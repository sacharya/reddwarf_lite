# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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
import weakref

from eventlet import greenthread

from reddwarf.common import excutils
from reddwarf.common import utils
from reddwarf.common import service
from reddwarf.taskmanager.tasks import InstanceTasks


LOG = logging.getLogger(__name__)


class TaskManager(service.Manager):
    """Task manager impl"""

    def __init__(self, *args, **kwargs):
        self.tasks = weakref.WeakKeyDictionary()
        #self.create_tasks()
        super(TaskManager, self).__init__(*args, **kwargs)
        LOG.info(_("TaskManager init %s %s") % (args, kwargs))

    def periodic_tasks(self, raise_on_error=False):
        LOG.debug("No. of running tasks: %r" % len(self.tasks))

    def _wrapper(self, method, context, *args, **kwargs):
        """Maps the respective manager method with a task counter."""
        # TODO(rnirmal): Just adding a basic counter. Will revist and
        # re-implement when we have actual tasks.
        self.tasks[greenthread.getcurrent()] = context
        try:
            func = getattr(self, method)
            return func(context, *args, **kwargs)
        except Exception as e:
            excutils.save_and_reraise_exception()
        finally:
            del self.tasks[greenthread.getcurrent()]

    def create_tasks(self):
        tasks = ['reddwarf.taskmanager.tasks.InstanceTasks']
        classes = []
        for task in tasks:
            LOG.info(task)
            task = utils.import_class(task)
            classes.append(task)
        try:
            cls = type("Tasks", tuple(set(classes)), {})
            self.task_driver = cls()
        except TypeError as te:
            msg = "An issue occurred instantiating the Tasks as the "\
                  "following classes: " + str(classes) +\
                  " Exception=" + str(te)
            raise TypeError(msg)

    def create_instance(self, context, instance_id, name, flavor_ref,
                        image_id, databases, service_type, volume_size ):
        LOG.info("Entering manager.create_instance")
        instance_tasks = InstanceTasks(context)
        instance_tasks.create_instance(context, instance_id, name, flavor_ref,
            image_id, databases, service_type, volume_size)

    def create_volume(self, context, instance_id, volume_size):
        LOG.info("Entering manager.create_volume")
        instance_tasks = InstanceTasks(context)
        instance_tasks.create_volume(context, instance_id, volume_size)

    def create_server(self, context, instance_id, name, flavor_ref, image_id,
                      service_type, block_device_mapping):
        LOG.info("Entering manager.create_server")
        instance_tasks = InstanceTasks(context)
        instance_tasks.create_server(context, instance_id, name, flavor_ref, image_id,
            service_type, block_device_mapping)

    def create_dns_entry(self, context, server_id, instance_id):
        LOG.info("Entering manager.create_dns_entry")
        instance_tasks = InstanceTasks(context)
        instance_tasks.create_dns_entry(context, server_id, instance_id)

    def guest_prepare(self, context, server, db_info, volume_info, databases):
        LOG.info("Entering manager.guest_prepare")
        instance_tasks = InstanceTasks(context)
        instance_tasks.guest_prepare(context, server, db_info, volume_info, databases)

