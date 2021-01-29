"""
azFindVMs.py: Finds running vms and their up-times on azure subscriptions that are accessible to the client.

To install dependencies:
pip install azure-cli
"""

__author__ = "Ewan Wai"

from azure.identity import AzureCliCredential
from azure.mgmt.resource import SubscriptionClient
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
import datetime


def find_running_vm(credentials):
    ''' Finds and prints information about azure VMs that are running '''
    running_vm_data = []

    subscription_client = SubscriptionClient(credentials)
    subscriptions = subscription_client.subscriptions.list()
    for subscription in subscriptions:  # iterate through subscriptions
        subscription_id = subscription.subscription_id
        subscription_name = subscription.display_name

        resource_client = ResourceManagementClient(credentials, subscription_id)
        resource_groups = resource_client.resource_groups.list()
        for resource_group in resource_groups:  # iterate through resource groups
            resource_group_name = resource_group.name

            compute_client = ComputeManagementClient(credentials, subscription_id)
            vms = compute_client.virtual_machines.list(resource_group_name)
            monitor_client = MonitorManagementClient(credentials, subscription_id)
            for vm in vms:
                vm_id = vm.id
                # get vm status, either 'PowerState/running', 'PowerState/deallocating'  or 'PowerState/deallocated'
                try:
                    status = compute_client.virtual_machines.instance_view(resource_group_name, vm.name).statuses[1].code
                except IndexError:
                    status = "Unknown"

                uptime = get_vm_uptime(vm_id, monitor_client)
                if uptime is not None:
                    uptime = int(uptime * 10) / 10  # shorten to 1 decimal point
                    running_vm_data.append([vm.name, str(uptime), resource_group_name, subscription_name])
                elif status == 'PowerState/running':  # check if the vm is running but logs didn't catch it (if running for >90 days)
                    running_vm_data.append([vm.name, '>90 days', resource_group_name, subscription_name])

    if len(running_vm_data) > 0:  # print info if any running vms were found
        print('{:^30s}{:^12s}{:^25s}{:^20s}'.format('Name', 'Uptime (hrs)', 'Resource Group', 'Subscription'))
        for vm_data in running_vm_data:
            print('{:^30s}{:^12s}{:^25s}{:^20s}'.format(vm_data[0], vm_data[1], vm_data[2], vm_data[3]))
    else:
        print('No running VMs found')


def get_vm_uptime(vm_id: str, monitor_client: MonitorManagementClient):
    '''
    Returns the uptime of an azure VM, using the activity logs, or returns None if it is stopped.
    Because azure only keeps logs for 90 days, uptime can only be found if running for less than 90 days.
    '''
    # azure deletes logs that are 90 days old so check from 89 days ago
    past_date = datetime.datetime.now() - datetime.timedelta(days=89)

    filter = " and ".join(["eventTimestamp ge '{}T00:00:00Z'".format(past_date.date()), "resourceUri eq '"+vm_id+"'"])
    logs = monitor_client.activity_logs.list(filter=filter)

    print(logs.next())
    
    for log in logs:  # iterate through logs from most recent
        if log.operation_name.value == 'Microsoft.Compute/virtualMachines/deallocate/action'\
                and log.status.value == 'Succeeded':
            #  if the most recent action was a successful de-allocation (means the machine is off)
            return None

        elif (log.operation_name.value == 'Microsoft.Compute/virtualMachines/start/action'
              or log.operation_name.value == 'Microsoft.Compute/virtualMachines/write') \
                and log.status.value == 'Succeeded':
            # if the most recent action was a successful start or creation (means the machine is running)
            start_time = log.event_timestamp
            now = datetime.datetime.now(datetime.timezone.utc)  # update now to be in UTC because the log is in UTC
            uptime = (now - start_time) / datetime.timedelta(hours=1)
            return uptime

    return None  # if for some reason no significant log was found, VM is assumed to not be running

if __name__ == '__main__':
    credentials = AzureCliCredential() # get credentials
    find_running_vm(credentials)