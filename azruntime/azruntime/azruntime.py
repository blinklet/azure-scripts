'''
List all VMs in your subscriptions in a formatted table.
The columns are: VM name, subscription, resource group, size, 
location, and status. Each row is a unique VM.

You must login to Azure CLI before you run this script:
$ az login

Prerequisites:
(env) $ pip install azure-mgmt-resource azure-mgmt-compute \
        azure-identity azure-cli-core rich azure-mgmt-monitor \
        rich
'''

from azure.mgmt.resource import SubscriptionClient as SubClient
from azure.mgmt.resource import ResourceManagementClient as ResourceClient
from azure.mgmt.compute import ComputeManagementClient as ComputeClient
from azure.mgmt.monitor import MonitorManagementClient as MonitorClient
from azure.identity import DefaultAzureCredential
from datetime import datetime, timezone, timedelta
from operator import itemgetter
from rich.console import Console
from rich.table import Table
from rich.progress import track
from rich.spinner import Spinner
from rich.live import Live
import time


def sublist(client):
    return [(sub.subscription_id, sub.display_name) for sub in client.subscriptions.list()] 


def grouplist(client):
    return [group.name for group in client.resource_groups.list()]


def vmlist(client, group):
    return [(vm.name, vm.id) for vm in client.virtual_machines.list(group)]


def vmsize(client, group, vm):
    return client.virtual_machines.get(group, vm).hardware_profile.vm_size


def vmlocation(client, group, vm):
    return client.virtual_machines.get(group, vm).location


def vmstatus(client, group, vm):
    ''' 
    Returns the power state of a VM instance. If there is no state to 
    read, returns state = "Unknown".
    '''
    # Sometimes, the instanceview.statuses list is empty or contains only one element.
    # This occurs when a VM fails to deploy properly but also it seems to
    # occasionally occur for no obvious reason. We check for it and move on.
    try:
        results = client.virtual_machines.instance_view(group, vm).statuses[1].code
    except IndexError:
        return 'Unknown'

    # Status code is always a two-part code, divided by a forward-slash.
    # The first is usually "PowerState" and the second is "running" or "deallocated".
    power, state = results.split('/')  
    return state


def diff_time(start_time, vm_status):
    """
    diff_time function calculates the time difference between the 
    start_time parameter and the present time. It returns a tuple. 
    The first item is string like '2 days, 4 hours' and the second 
    item is a string for the style argument used to style the row. 
    We use different styles to running highlight VMs that have been 
    running too long, or deallocated VMs that are too old.
    """
    now = datetime.now(timezone.utc)
    uptime = (now - start_time) / timedelta(hours=1)
    uptime_string = ""
    style_tag = ""
    
    uptime_days = int(uptime) // 24
    uptime_hours = int(uptime) % 24

    # set color for row style
    if vm_status == "running":
        if uptime_days == 0:
            style_tag = "dark_sea_green4"
        elif uptime_days == 1:
            style_tag = "gold1"
        elif uptime_days == 2:
            style_tag = "dark_orange"
        elif uptime_days >= 3:
             style_tag = "orange_red1"
    elif vm_status == "deallocated":
        if uptime_days < 14:
            style_tag = "dark_sea_green4 dim"
        elif uptime_days >= 14 and uptime_days <= 28:
            style_tag = "gold1 dim"
        elif uptime_days > 28:
            style_tag = "dark_orange dim"
    else:
        raise ValueError("vm_status is not expected value")

    # build string to return
    if uptime_days == 0:
        uptime_string = str(uptime_hours) + ' hours'
    else:
        uptime_string = str(uptime_days) + ' days, '+ str(uptime_hours) + ' hours'

    return uptime_string, style_tag


def get_vm_time(vm_id, monitor_client, vm_status='running'):
    '''
    Looks for most recent startup or shutdown log and returns a tuple. 
    First returned item is the time delta and the second returned item 
    is a style that another function uses to set the colors in the 
    output table.
    '''
    # If you filter using a date older than 89 days, you may see 
    # an error message like: "msrest.exceptions.DeserializationError"
    past_date = datetime.now(timezone.utc) - timedelta(days=89)

    filter = " and ".join([
        f"eventTimestamp ge '{past_date.date()}T00:00:00Z'",
        f"resourceUri eq '{vm_id}'"
    ])
    
    select = ','.join([
        'operationName',
        'eventTimestamp',
        'status'
    ])

    logs = monitor_client.activity_logs.list(filter=filter, select=select)

    for log in logs:
        if vm_status == 'deallocated':
            # Look for the most recent successful deallocation log
            vm_deallocated = (log.operation_name.value == 'Microsoft.Compute/virtualMachines/deallocate/action')
            succeeded = (log.status.value == 'Succeeded')
            
            if vm_deallocated and succeeded:
                return diff_time(log.event_timestamp, vm_status)

        elif vm_status == 'running':
            # Look for the most recent successful start or creation log
            vm_started = (log.operation_name.value == 'Microsoft.Compute/virtualMachines/start/action')
            vm_created = (log.operation_name.value == 'Microsoft.Compute/virtualMachines/write')
            succeeded = (log.status.value == 'Succeeded')
            
            if (vm_started or vm_created) and succeeded:
                return diff_time(log.event_timestamp, vm_status)

        else:
            return "invalid vm_status", "blue"  # to catch programming errors 

    # If the loop completes without finding a successful VM start or create log,
    # or if the logs iterator is empty (so loop does not execute), 
    # VM has been running for more than 90 days.
    if vm_status == "running":
        return '>90 days', "red3 bold"
    else:
        return '>90 days', "red3 dim"


def build_vm_list(credentials):
    ''' 
    Build a list of all VMs in all the subscriptions visible to the user.
    The returned list contains nested lists, one header list, and one list
    for each VM. Each nested list contains the VM name, subscription, 
    resource group, size, location, status, and uptime.
    The style column will be removed before the table is displayed.
    '''
    headers = ['VM name','Subscription','ResourceGroup','Size','Location','Status','TimeInState','style']

    returned_list = list()
    returned_list.append(headers)

    newconsole = Console()

    with newconsole.status("[green]Getting subscriptions[/green]") as status:

        subscription_client = SubClient(credentials)
        subscriptions = sublist(subscription_client)

        for subscription_id, subscription_name in subscriptions:

            resource_client = ResourceClient(credentials, subscription_id)
            compute_client = ComputeClient(credentials, subscription_id)
            monitor_client = MonitorClient(credentials, subscription_id)
            resource_groups = grouplist(resource_client)

            for resource_group in resource_groups:
                vms = vmlist(compute_client, resource_group)

                for vm_name, vm_id in vms:

                    status.update(status="[grey74]Subscription: [/grey74][green4]" + subscription_name + "[/green4][grey74]  Resource Group: [/grey74][green4]" + resource_group + "[/green4][grey74]  VM: [/grey74][green4]" + vm_name + "[/green4]")

                    vm_status = vmstatus(compute_client, resource_group, vm_name)
                    vm_size = vmsize(compute_client, resource_group, vm_name)
                    vm_location = vmlocation(compute_client, resource_group, vm_name)

                    if vm_status == 'running':
                        vm_time, style_tag = get_vm_time(vm_id, monitor_client, vm_status="running")
                    elif vm_status == "deallocated":
                        vm_time, style_tag = get_vm_time(vm_id, monitor_client, vm_status="deallocated")
                    elif vm_status == 'Unknown':
                        vm_time, style_tag = 'Unknown', 'sky_blue3'
                    else:
                        vm_time, style_tag = '???', 'sky_blue3'  # if unexpected result

                    returned_list.append([
                        vm_name, 
                        subscription_name, 
                        resource_group, 
                        vm_size, 
                        vm_location, 
                        vm_status, 
                        vm_time, 
                        style_tag
                    ])

        return returned_list


def sort_by_column(input_list, *sort_keys):
    ''' Sort a list by columns, except for the first row '''
    
    headers = input_list[0]
    list_to_sort = input_list[1:]
    x = [headers.index(column) for column in sort_keys]

    list_to_sort.sort(key=itemgetter(*x))
    list_to_sort.insert(0, headers)
    return list_to_sort


def vm_table():
    credentials = DefaultAzureCredential(
        exclude_environment_credential = True,
        exclude_managed_identity_credential = True,
        exclude_shared_token_cache_credential = True,
        exclude_visual_studio_code_credential = True,
        exclude_interactive_browser_credential = False
    )
    vm_list = build_vm_list(credentials)

    if len(vm_list) > 1:  # An empty vm_list still has a header row
        sorted_list = sort_by_column(vm_list,'Status','ResourceGroup','Size')

        table = Table(show_header=True, header_style="bold", show_lines=True)

        # the column headers are in the first row of the list
        # remove style column from header row
        header_list = sorted_list[0][:-1] 
        for column_name in header_list: 
            table.add_column(column_name)

        # Each row is a nested list.
        # Unpack each nested list into arguments for the add_row function
        # Get the row's style from the last column in each row
        # but discard the style column before adding the row
        for row in sorted_list[1:]:
            style_tag = row.pop() # pop style column off row
            table.add_row(*row, style=style_tag)

        return table
    else:
        return "No VMs found"

def main():
    console = Console()
    console.print(vm_table())

if __name__ == '__main__':
    main()
    