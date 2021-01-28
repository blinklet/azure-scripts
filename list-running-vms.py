"""
List all VMs in your subscriptions in a formatted table

You must login to Azure CLI before you run this script:
$ az login

Prerequisites:
(env) $ pip install azure-mgmt-resource azure-mgmt-compute azure-identity azure-cli-core tabulate
"""

from azure.mgmt.resource import SubscriptionClient as SubClient
from azure.mgmt.resource import ResourceManagementClient as ResourceClient
from azure.mgmt.compute import ComputeManagementClient as ComputeClient
from azure.identity import AzureCliCredential
from tabulate import tabulate


def sublist(client):
    return([sub.subscription_id for sub in client.subscriptions.list()])


def grouplist(client):
    return([group.name for group in client.resource_groups.list()])


def vmlist(client, group):
    return([vm.name for vm in client.virtual_machines.list(group)])


def vmstatus(client, group, vm):
    # Sometimes, the instanceview.statuses list is empty or contains only one element
    # This seems like a random problem in Azure so we check for it and move on
    try:
        results = client.virtual_machines.instance_view(group, vm).statuses[1].code
    except IndexError:
        results = "Unknown"
    return(results)


def vmsize(client, group, vm):
    return(client.virtual_machines.get(group, vm).hardware_profile.vm_size)


def vmlocation(client, group, vm):
    return(client.virtual_machines.get(group, vm).location)


def build_vm_table(credentials):
    headers = ['VM name','ResourceGroup','Size','Location','Status']
    table = list()
    table.append(headers)

    subscription_client = SubClient(credentials)
    subscription_ids = sublist(subscription_client)
    for subscription_id in subscription_ids:
        resource_client = ResourceClient(credentials, subscription_id)
        resource_groups = grouplist(resource_client)
        for resource_group in resource_groups:
            compute_client = ComputeClient(credentials, subscription_id)
            vms = vmlist(compute_client, resource_group)
            for vm in vms:
                vm_status = vmstatus(compute_client, resource_group, vm)
                vm_size = vmsize(compute_client, resource_group, vm)
                vm_location = vmlocation(compute_client, resource_group, vm)
                table.append([vm, resource_group, vm_size, vm_location, vm_status])

    return(table)


def print_table(input_list):
    formatted_table = tabulate(input_list, headers='firstrow', tablefmt='pretty')
    print(formatted_table)


def sort_status(input_list):
    # Sort the table by the Status field, except for the first row
    new_list = list()
    new_list.append(input_list[0])
    for row in sorted(input_list[1:], key = lambda x: x[4]):
        new_list.append(row)
    return(new_list)


if __name__ == '__main__':
    credentials = AzureCliCredential()
    print_table(sort_status(build_vm_table(credentials)))