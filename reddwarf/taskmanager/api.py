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


"""
Routes all the requests to the task manager.
"""


import logging

from reddwarf import rpc
from reddwarf.common import config
from reddwarf.common import exception
from reddwarf.common import utils


LOG = logging.getLogger(__name__)


class API(object):
    """API for interacting with the task manager."""

    def __init__(self, context):
        self.context = context

    def _call(self, method_name, **kwargs):
        LOG.debug("Calling %s" % method_name)
        try:
            result = rpc.call(self.context, self._get_routing_key(),
                            {"method": method_name, "args": kwargs})
            LOG.debug("Result is %s" % result)
            return result
        except Exception as e:
            LOG.error(e)
            raise exception.TaskManagerError(original_message=str(e))

    def _cast(self, method_name, **kwargs):
        LOG.debug("Calling %s" % method_name)
        try:
            rpc.cast(self.context, self._get_routing_key(),
                    {"method": method_name, "args": kwargs})
        except Exception as e:
            LOG.error(e)
            raise exception.TaskManagerError(original_message=str(e))

    def _get_routing_key(self):
        """Create the routing key for the taskmanager"""
        return "taskmanager"

    def create_volume(self, instance_id, volume_size):
        return self._call("create_volume", instance_id=instance_id,
                            volume_size=volume_size)

    def create_dns_entry(self, server_id, instance_id):
        return self._cast("create_dns_entry", server_id=server_id,
                            instance_id=instance_id)

    def create_instance(self, instance_id, name, flavor_ref, image_id,
                        databases, service_type, volume_size):
        return self._cast("create_instance", instance_id=instance_id,
            name=name, flavor_ref=flavor_ref,
            image_id=image_id, databases=databases,
            service_type=service_type,
            volume_size=volume_size)

