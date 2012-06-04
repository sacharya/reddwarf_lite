# Copyright 2012 OpenStack LLC.
# All Rights Reserved.
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
from reddwarf.common import exception as rd_exceptions
from reddwarf.common.remote import create_nova_volume_client
from reddwarf.common.remote import create_dns_client
from reddwarf.common.remote import create_nova_client
from reddwarf.instance.models import DBInstance
from reddwarf.instance.views import get_ip_address

LOG = logging.getLogger(__name__)

class InstanceTasks(object):

    def __init__(self):
        pass

    def create_volume(self, context, instance_id, volume_size):
        LOG.info("Entering create_volume")
        LOG.debug(_("Starting to create the volume for the instance"))

        db_info = DBInstance.find_by(id=instance_id)

        volume_client = create_nova_volume_client(context)
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
            raise rd_exceptions.VolumeCreationFailure()
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

    def create_dns_entry(self, context, server_id, instance_id):
        LOG.info("Creating dns entry...")

        # Get the Ip address
        client = create_nova_client(context)
        server = client.servers.get(server_id)
        while(server.addresses == {}):
            import time
            time.sleep(1)
            server = client.servers.get(server_id)
            LOG.debug("Waiting for address %s" % server.addresses)

        # Update the hostname
        db_info = DBInstance.find_by(id=instance_id)
        dns_client = create_dns_client(context)
        dns_client.update_hostname(db_info)

        # Update Dns entry
        dns_client.create_instance_entry(instance_id, get_ip_address(server.addresses))
        LOG.info("Finished")

