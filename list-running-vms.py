"""
List all VMs in your subscriptions in a formatted table.
The columns are: VM name, subscription, resource group, size, location, and status.
Each row is a unique VM.

You must login to Azure CLI before you run this script:
$ az login

Usage:
$ python list-running-vms.py -f|--format <format> -s|--subscription_id <id>

Prerequisites:
(env) $ pip install azure-mgmt-resource azure-mgmt-compute azure-identity azure-cli-core tabulate
"""

from azure.mgmt.resource import SubscriptionClient as SubClient
from azure.mgmt.resource import ResourceManagementClient as ResourceClient
from azure.mgmt.compute import ComputeManagementClient as ComputeClient
from azure.identity import AzureCliCredential
from azure.identity._exceptions import CredentialUnavailableError,
from tabulate import tabulate


def sublist(client):
    return([(sub.subscription_id, sub.display_name) for sub in client.subscriptions.list()])


def grouplist(client):
    return([group.name for group in client.resource_groups.list()])


def vmlist(client, group):
    return([vm.name for vm in client.virtual_machines.list(group)])


def vmstatus(client, group, vm):
    # Sometimes, the instanceview.statuses list is empty or contains only one element.
    # This seems like a random problem in Azure so we check for it and move on.
    try:
        results = client.virtual_machines.instance_view(group, vm).statuses[1].code
    except IndexError:
        results = "Unknown"
    return(results)


def vmsize(client, group, vm):
    return(client.virtual_machines.get(group, vm).hardware_profile.vm_size)


def vmlocation(client, group, vm):
    return(client.virtual_machines.get(group, vm).location)


def build_vm_list(credentials):
    ''' 
    Build a list of all VMs in all the subscriptions visible to the user.
    The returned list contains nested lists, one header list and one list
    for each VM. Each nested list contains the VM name, subscription, 
    resource group, size, location, and status.
    '''
    headers = ['VM name','Subscription','ResourceGroup','Size','Location','Status']
    returned_list = list()
    returned_list.append(headers)

    subscription_client = SubClient(credentials)
    subscriptions = sublist(subscription_client)
    for subscription_id, subscription_name in subscriptions:
        resource_client = ResourceClient(credentials, subscription_id)
        resource_groups = grouplist(resource_client)
        for resource_group in resource_groups:
            compute_client = ComputeClient(credentials, subscription_id)
            vms = vmlist(compute_client, resource_group)
            for vm in vms:
                vm_status = vmstatus(compute_client, resource_group, vm)
                vm_size = vmsize(compute_client, resource_group, vm)
                vm_location = vmlocation(compute_client, resource_group, vm)
                returned_list.append([vm, subscription_name, resource_group, vm_size, vm_location, vm_status])

    return(returned_list)


def sort_by_status(input_list):
    ''' Sort a list by the Status field, except for the first row '''
    new_list = list()
    new_list.append(input_list[0])
    for row in sorted(input_list[1:], key = lambda x: x[5]):
        new_list.append(row)
    return(new_list)


def print_table(input_list, frmt):
    formatted_table = tabulate(input_list, headers='firstrow', tablefmt=frmt)
    print(formatted_table)


def vm_table(tablefmt):
    credentials = AzureCliCredential()
    vm_list = build_vm_list(credentials)
    sorted_list = sort_by_status(vm_list)
    print_table(sorted_list,tablefmt)


if __name__ == '__main__':
    vm_table('pretty')   # Choose one of the formats supported by the tabular library