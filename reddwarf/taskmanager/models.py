#    Copyright 2012 OpenStack LLC
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging

from eventlet import greenthread

from reddwarf.common import config
from reddwarf.common import exception
from reddwarf.common import remote
from reddwarf.common import utils
from reddwarf.common.exception import ReddwarfError
from reddwarf.common.exception import VolumeCreationFailure
from reddwarf.common.remote import create_dns_client
from reddwarf.common.remote import create_guest_client
from reddwarf.common.remote import create_nova_client
from reddwarf.common.remote import create_nova_volume_client
from reddwarf.common.utils import poll_until
from reddwarf.instance import models as inst_models
from reddwarf.instance.models import DBInstance
from reddwarf.instance.models import InstanceStatus
from reddwarf.instance.models import InstanceServiceStatus
from reddwarf.instance.models import populate_databases
from reddwarf.instance.models import ServiceStatuses
from reddwarf.instance.views import get_ip_address


LOG = logging.getLogger(__name__)


class InstanceTasks:
    """
    Performs the various asynchronous instance related tasks.
    """

    def __init__(self, context, db_info=None, server=None, volumes=None,
                 nova_client=None, volume_client=None, guest=None):
        self.context = context
        self.db_info = db_info
        self.server = server
        self.volumes = volumes
        self.nova_client = nova_client
        self.volume_client = volume_client
        self.guest = guest

    @property
    def volume_id(self):
        return self.volumes[0]['id']

    @property
    def volume_mountpoint(self):
        mountpoint = self.volumes[0]['mountpoint']
        if mountpoint[0] is not "/":
            return "/%s" % mountpoint
        else:
            return mountpoint

    @staticmethod
    def load(context, id):
        if context is None:
            raise TypeError("Argument context not defined.")
        elif id is None:
            raise TypeError("Argument id not defined.")
        try:
            db_info = inst_models.DBInstance.find_by(id=id)
        except exception.NotFound:
            raise exception.NotFound(uuid=id)
        server, volumes = inst_models.load_server_with_volumes(context,
                                                db_info.id,
                                                db_info.compute_instance_id)
        nova_client = remote.create_nova_client(context)
        volume_client = remote.create_nova_volume_client(context)
        guest = remote.create_guest_client(context, id)
        return InstanceTasks(context, db_info, server, volumes,
                             nova_client=nova_client,
                             volume_client=volume_client, guest=guest)

    def resize_volume(self, new_size):
        LOG.debug("%s: Resizing volume for instance: %s to %r GB"
                  % (greenthread.getcurrent(), self.server.id, new_size))
        self.volume_client.volumes.resize(self.volume_id, int(new_size))
        try:
            utils.poll_until(
                        lambda: self.volume_client.volumes.get(self.volume_id),
                        lambda volume: volume.status == 'in-use',
                        sleep_time=2,
                        time_out=int(config.Config.get('volume_time_out')))
            self.nova_client.volumes.rescan_server_volume(self.server,
                                                          self.volume_id)
            self.guest.resize_fs(self.volume_mountpoint)
        except exception.PollTimeOut as pto:
            LOG.error("Timeout trying to rescan or resize the attached volume "
                      "filesystem for volume: %s" % self.volume_id)
        except Exception as e:
            LOG.error("Error encountered trying to rescan or resize the "
                      "attached volume filesystem for volume: %s"
                      % self.volume_id)
        finally:
            self.db_info.task_status = inst_models.InstanceTasks.NONE
            self.db_info.save()

    def _create_volume(self, instance_id, volume_size):
        LOG.info("Entering create_volume")
        LOG.debug(_("Starting to create the volume for the instance"))

        db_info = DBInstance.find_by(id=instance_id)

        volume_client = create_nova_volume_client(self.context)
        volume_desc = ("mysql volume for %s" % instance_id)
        volume_ref = volume_client.volumes.create(
            volume_size,
            display_name="mysql-%s" % db_info.id,
            display_description=volume_desc)
        # Record the volume ID in case something goes wrong.
        db_info.volume_id = volume_ref.id
        db_info.save()
        #TODO(cp16net) this is bad to wait here for the volume create
        # before returning but this was a quick way to get it working
        # for now we need this to go into the task manager
        v_ref = volume_client.volumes.get(volume_ref.id)
        while not v_ref.status in ['available', 'error']:
            LOG.debug(_("waiting for volume [volume.status=%s]") %
                      v_ref.status)
            greenthread.sleep(1)
            v_ref = volume_client.volumes.get(volume_ref.id)

        if v_ref.status in ['error']:
            raise VolumeCreationFailure()
        LOG.debug(_("Created volume %s") % v_ref)
        # The mapping is in the format:
        # <id>:[<type>]:[<size(GB)>]:[<delete_on_terminate>]
        # setting the delete_on_terminate instance to true=1
        mapping = "%s:%s:%s:%s" % (v_ref.id, '', v_ref.size, 1)
        bdm = config.Config.get('block_device_mapping', 'vdb')
        block_device = {bdm: mapping}
        volumes = [{'id': v_ref.id,
                    'size': v_ref.size}]
        LOG.debug("block_device = %s" % block_device)
        LOG.debug("volume = %s" % volumes)

        device_path = config.Config.get('device_path', '/dev/vdb')
        mount_point = config.Config.get('mount_point', '/var/lib/mysql')
        LOG.debug(_("device_path = %s") % device_path)
        LOG.debug(_("mount_point = %s") % mount_point)

        volume_info = {'block_device': block_device,
                       'device_path': device_path,
                       'mount_point': mount_point,
                       'volumes': volumes}
        return volume_info

    def _create_server(self, instance_id, name, flavor_ref, image_id,
                      service_type, block_device_mapping):
        nova_client = create_nova_client(self.context)
        files = {"/etc/guest_info": "guest_id=%s\nservice_type=%s\n" %
                                    (instance_id, service_type)}
        server = nova_client.servers.create(name, image_id, flavor_ref,
                                       files=files, block_device_mapping=block_device_mapping)
        LOG.debug(_("Created new compute instance %s.") % server.id)
        return server

    def _guest_prepare(self, server, db_info, volume_info, databases):
        LOG.info("Entering guest_prepare")
        db_info.compute_instance_id = server.id
        db_info.save()
        service_status = InstanceServiceStatus.create(instance_id=db_info.id,
                                                      status=ServiceStatuses.NEW)
        # Now wait for the response from the create to do additional work

        guest = create_guest_client(self.context, db_info.id)

        # populate the databases
        model_schemas = populate_databases(databases)
        guest.prepare(512, model_schemas, users=[],
                      device_path=volume_info['device_path'],
                      mount_point=volume_info['mount_point'])

    def create_instance(self, instance_id, name, flavor_ref,
                    image_id, databases, service_type, volume_size):
        LOG.info("Entering create_instance")
        try:
            db_info = DBInstance.find_by(id=instance_id)
            volume_info = self._create_volume(instance_id,
                                             volume_size)
            block_device_mapping = volume_info['block_device']
            server = self._create_server(instance_id, name,
                                        flavor_ref, image_id, service_type,block_device_mapping)
            LOG.info("server id: %s" % server)
            server_id = server.id
            self._create_dns_entry(instance_id, server_id)
            LOG.info("volume_info %s " % volume_info)
            self._guest_prepare(server, db_info, volume_info, databases)
        except Exception, e:
            LOG.error(e)

    def _create_dns_entry(self, instance_id, server_id):
        LOG.debug("%s: Creating dns entry for instance: %s"
                  % (greenthread.getcurrent(), instance_id))
        dns_client = create_dns_client(self.context)
        dns_support = config.Config.get("reddwarf_dns_support", 'False')
        LOG.debug(_("reddwarf dns support = %s") % dns_support)

        nova_client = create_nova_client(self.context)
        if utils.bool_from_string(dns_support):
            def get_server():
                return nova_client.servers.get(server_id)

            def ip_is_available(server):
                LOG.info("Polling for ip addresses: $%s " % server.addresses)
                if server.addresses != {}:
                    return True
                elif server.addresses == {} and\
                     server.status != InstanceStatus.ERROR:
                    return False
                elif server.addresses == {} and\
                     server.status == InstanceStatus.ERROR:
                     LOG.error(_("Instance IP not available, instance (%s): "
                                 "server had status (%s).")
                                 % (instance_id, server.status))
                     raise ReddwarfError(status=server.status)
            poll_until(get_server, ip_is_available,
                       sleep_time=1, time_out=60 * 2)
            server = nova_client.servers.get(server_id)
            LOG.info("Creating dns entry...")
            dns_client.create_instance_entry(instance_id,
                                        get_ip_address(server.addresses))

