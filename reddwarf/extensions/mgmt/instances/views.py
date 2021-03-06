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


from reddwarf.instance.views import InstanceDetailView


class MgmtInstanceView(InstanceDetailView):

    def __init__(self, instance, req=None, add_addresses=False,
                 add_volumes=False):
        super(MgmtInstanceView, self).__init__(instance, req,
                                               add_addresses,
                                               add_volumes)

    def data(self):
        result = super(MgmtInstanceView, self).data()
        if self.instance.server is None:
            result['instance']['server'] = None
        else:
            server = self.instance.server
            result['instance']['server'] = {
                'deleted': server.deleted,
                'deleted_at': server.deleted_at,
                'host': server.host,
                'id': server.id,
                'local_id': server.local_id,
                'name': server.name,
                'status': server.status,
                'tenant_id': server.tenant_id,
            }

        try:
            service_status = self.instance.service_status.status.api_status
        except AttributeError:
            service_status = None
        result['instance']['service_status'] = service_status
        result['instance']['tenant_id'] = self.instance.tenant_id
        result['instance']['deleted'] = bool(self.instance.deleted)
        result['instance']['deleted_at'] = self.instance.deleted_at
        result['instance']['task_description'] = self.instance.task_description
        return result


class MgmtInstanceDetailView(MgmtInstanceView):
    """Works with a full-blown instance."""

    def __init__(self, instance, req, add_addresses=False,
                 add_volumes=False, root_history=None):
        add_a = add_addresses
        super(MgmtInstanceDetailView, self).__init__(instance,
                                                     req=req,
                                                     add_addresses=add_a,
                                                     add_volumes=add_volumes)
        self.root_history = root_history

    def data(self):
        result = super(MgmtInstanceDetailView, self).data()
        if self.instance.server is not None:
            server = self.instance.server
            result['instance']['server'].update(
                {'addresses': server.addresses})
        if self.root_history:
            result['instance']['root_enabled'] = self.root_history.created
            result['instance']['root_enabled_by'] = self.root_history.user
        if self.instance.volume:
            volume = self.instance.volume
            result['instance']['volume'] = {
                "attachments": volume.attachments,
                "availability_zone": volume.availability_zone,
                "created_at": volume.created_at,
                "id": volume.id,
                "size": volume.size,
                "status": volume.status,
            }
        else:
            result['instance']['volume'] = None
        description = self.instance.service_status.status.description
        result['instance']['guest_status'] = {"state_description": description}
        return result


class MgmtInstancesView(object):
    """Shows a list of MgmtInstance objects."""

    def __init__(self, instances, req=None, add_addresses=False,
                 add_volumes=False):
        self.instances = instances
        self.req = req
        self.add_addresses = add_addresses
        self.add_volumes = add_volumes

    def data(self):
        data = []
        # These are model instances
        for instance in self.instances:
            data.append(self.data_for_instance(instance))
        return {'instances': data}

    def data_for_instance(self, instance):
        view = MgmtInstanceView(instance, req=self.req,
                                add_addresses=self.add_addresses,
                                add_volumes=self.add_volumes)
        return view.data()['instance']


class RootHistoryView(object):

    def __init__(self, instance_id, enabled='Never', user_id='Nobody'):
        self.instance_id = instance_id
        self.enabled = enabled
        self.user = user_id

    def data(self):
        return {
            'root_history': {
                'id': self.instance_id,
                'enabled': self.enabled,
                'user': self.user,
            }
        }


class HwInfoView(object):

    def __init__(self, instance_id, hwinfo):
        self.instance_id = instance_id
        self.hwinfo = hwinfo

    def data(self):
        return {
            'hwinfo': {
                'mem_total': self.hwinfo['mem_total'],
                'num_cpus': self.hwinfo['num_cpus'],
            }
        }


class DiagnosticsView(object):

    def __init__(self, instance_id, diagnostics):
        self.instance_id = instance_id
        self.diagnostics = diagnostics

    def data(self):
        return {
            'diagnostics': {
                'version': self.diagnostics['version'],
                'threads': self.diagnostics['threads'],
                'fdSize': self.diagnostics['fd_size'],
                'vmSize': self.diagnostics['vm_size'],
                'vmPeak': self.diagnostics['vm_peak'],
                'vmRss': self.diagnostics['vm_rss'],
                'vmHwm': self.diagnostics['vm_hwm'],
            }
        }
