#!/usr/bin/env python
# coding: utf-8

# In[1]:


# Import required libraries
# Version 5.4

import pandas as pd
import os
import re
import sys
import subprocess
import requests
import hashlib
import logging
from datetime import datetime
from itertools import islice


# In[2]:


# Check version from Github
GITHUB_FILE_URL = "https://raw.githubusercontent.com/pranav-kaushal/Nokia/refs/heads/main/NNI/NNI_121to135LLD.py"
cwd = os.getcwd()
LOCAL_FILE_PATH  = os.path.join(cwd, "NNI_121to135LLD.py") # Path for the current script file
print(cwd)
def get_remote_file_content(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.content
    else:
        print(f"Failed to retrieve file. Status code: {response.status_code}")
        return None

def get_file_hash(content):
    return hashlib.md5(content).hexdigest()

def check_for_update():
    new_content = get_remote_file_content(GITHUB_FILE_URL)
    if not new_content:
        return False  # No update due to a fetch issue
    with open(LOCAL_FILE_PATH, "rb") as f:
        current_content = f.read()
    if get_file_hash(new_content) != get_file_hash(current_content):
        print("Update found! Updating script...")
        with open(LOCAL_FILE_PATH, "wb") as f:
            f.write(new_content)
        return True
    else:
        print("No update found.")
        return False

def restart_script():
    print("Restarting script...")
    subprocess.Popen([sys.executable] + sys.argv)
    sys.exit()  # Close the current script


# In[3]:


def scan_file():
    global my_files
    global cwd
    my_files = []
    cwd = os.getcwd() # check for the file in current directory
    file_path = os.listdir(cwd) # list the files
    for i in file_path:
        if '.cfg' in i or '.log' in i: # Chage this to .txt, or .cfg or .log based on your files.
            my_files.append(i)
    return (my_files, cwd)


# In[4]:


# Create a list of path for all the scanned files above.
def all_files():
    scan_file()
    global path
    path = []
    for i in range(len(my_files)):
        path.append(cwd+"/"+my_files[i])
    return path


# In[5]:


# Read the contents and extract the file name
def create_pd():

    global name, my_file_pd, router_type, ecmp_value, system_ip

    my_file_pd = pd.read_fwf(items, index_col=False, header=None,sep = ' ' )
    my_file_pd = my_file_pd.rename(columns = {0 : "config"})
    # Get site name
    site_name = my_file_pd.index[my_file_pd['config'].str.contains("name")]
    name = my_file_pd['config'][site_name[0]]
    name = name[6:-1].strip('"')
    
    # Search for rows containing 7705, 7750, or 7250
    search_terms = ['7705', '7250', '7750']
    for line in my_file_pd['config']:
        match = re.search(r'(7705|7250)', line)
        if match:
            router_type = match.group()
            #print(router_type)
        #Check for ecmp on IXRE B4C
    try:
        ecmp = my_file_pd['config'].index[my_file_pd['config'].str.contains(r'ecmp \d{1}', regex=True)] # 1 nos in ecmp
        ecmp = my_file_pd['config'][ecmp[0]]
        ecmp_value = ecmp.split()
        #print(ecmp_value[1])
    except IndexError:
        print("# No ecmp found")
    
    sys = my_file_pd.index[my_file_pd['config'].str.contains('router-id')]
    router_id_row = my_file_pd['config'][sys].iloc[0]
    match = re.search(r'router-id\s+(\d+\.\d+\.\d+\.\d+)', router_id_row)
    if match:
        system_ip = match.group(1)
        #print(f"Extracted IP address: {system_ip}")
    else:
        print("No IP address found.")
        


# In[6]:


def get_bof(data):
    global bof_address_ip, static_next_hop
    bof_address_ip = None
    static_next_hop = None
    
    try:
        group_start_idx = data[data['config'].str.contains('BOF \(Memory\)')].index[0]
        group_end_idx = data[data['config'].str.contains('persist')].index[0]
        for i in range(group_start_idx, group_end_idx):
            line = data.at[i, 'config'].strip()
            if line.startswith('address') or line.startswith('eth-mgmt-address'):
                bof_address_ip = line.split()[1]
            if line.startswith('static-route') or line.startswith('eth-mgmt-route') and static_next_hop is None:
                static_next_hop = line.split('next-hop')[1].strip()
                break  # Just the first static
    except IndexError:
        print("No BOF address or static route found. Please check the config manually")
    
    #return bof_address_ip, static_next_hop
def bof_data():
    global static_route_new_1, static_route_new_2, static_route_new_3, old_statics
    get_bof(my_file_pd)
    ## Create new static routes
    static_route_new_1 = "/bof static-route 2001:4888::/32 next-hop " + static_next_hop
    static_route_new_2 = "/bof static-route 2600::/16 next-hop " + static_next_hop
    static_route_new_3 = "/bof static-route 2607::/16 next-hop " + static_next_hop
    
    ## Remove of old static routes
    combined ='next-hop ' + static_next_hop
    # Get old static routes from config file based on gw from vpls400 and next-hop keyword
    #old_statics = my_file_pd['config'].index[my_file_pd['config'].str.contains(combined)]
    if combined[-2:] == "::":
        comb = 'next-hop ' + static_next_hop[0:-2] #+ ":0:0"
        old_statics = my_file_pd['config'].index[my_file_pd['config'].str.contains(comb, flags=re.I)]
    else:
        old_statics = my_file_pd['config'].index[my_file_pd['config'].str.contains(combined)]
    return old_statics

def create_bof(old_statics):
    get_bof(my_file_pd)
    bof_data()
    print('')
    print('#--------------------------------------------------')
    print('#System Name: {}"'.format(name))
    print('#--------------------------------------------------')
    print('########### Adding the New Static Routes ############')
    print('')
    print(static_route_new_1)
    print(static_route_new_2)
    print(static_route_new_3)
    print('/bof speed 1000')
    print('')
    print('')
    print('#--------------------------------------------------')
    print('########### Removing Old Static Routes ############')
    print('#--------------------------------------------------')
    print('/show bof')
    print('')
    for rts in old_statics:
        routes = my_file_pd['config'][rts]
        routes = re.sub(r' {4,}', ' ', routes)
        print("/bof no", routes)


# In[7]:


# Get the interfaces for which the metric has to be changed.
def metric_nni(data):
    global met_int_b4c, met_int_b40
    met_int_b4c = {}
    met_int_b40= {}
    
    try:
        # Find the start of search keywordac
        group_start_idx = data[data['config'].str.fullmatch('router Base')].index[0] 
        group_end_idx = data[data['config'].str.match('echo "Service')].index[0]
        
        in_neighbor_block = False #Use a flag in_neighbor_block to track if we are within a neighbor block.
        interface_desc = None
    
        for i in range(group_start_idx, group_end_idx):
            line = data.at[i, 'config'].strip()
            
            if line.startswith('interface'):
                in_neighbor_block = True
                interface_desc = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if 'B4C' in description:  
                    met_int_b4c[interface_desc] = description
                if 'B40' in description:  
                    met_int_b40[interface_desc] = description
                in_neighbor_block = False
            elif line == 'exit':
                in_neighbor_block = False
    except IndexError:
        print("No B4C/B40 interface was found, Please check the config manually")

    return met_int_b4c, met_int_b40

def metric_interface_nni(): # Interface output 
    
    met_int_b4c, met_int_b40 = metric_nni(my_file_pd)

    print('')
    if ecmp_value[1] != '1':
        print('#--------------------------------------------------')
        print("# This router has ecmp value {}, please change it to ecmp 1".format(ecmp_value[1]))
        print('#--------------------------------------------------')
        print('/configure router ecmp 1')
    print('#--------------------------------------------------')
    print('# New Interface Configuration')
    print('#--------------------------------------------------')
    print('')
    for interface_desc, description in met_int_b40.items():
        print('/configure router isis 5 interface {} level 1 metric 1000000'.format(interface_desc))
    print('')
    print('/configure router interface "system" bfd 100 receive 100 multiplier 3')
    print('')
    print('#--------------------------------------------------')
    print('# Update ISIS 5 overload timout')
    print('#--------------------------------------------------')
    print('')
    print('/configure router isis 5 overload-on-boot timeout 180')   
    print('')


# In[8]:


####### Search the existing HUB policy with LL and NON LL b40 ips    ###################
def extract_LL_bgp_neighbors(data, start_key, end_key, find_value):
    global return_value, cluster
    return_value = {}
    cluster = None

    try:
        # Find the start and end of the start_key
        group_start_idx = data[data['config'].str.contains(start_key)].index[0]
        group_end_idx = data[data['config'].str.contains(end_key)].index[0]
        
        in_neighbor_block = False
        current_neighbor_ip = None
        current_import_line = None  # Variable to hold the import line
        
        for i in range(group_start_idx, group_end_idx):
            line = data.at[i, 'config'].strip()

            # Capture the cluster value if it exists
            if line.startswith('cluster'):
                cluster = line.split()[1]  # Store the cluster IP
            
            # Start tracking neighbor IP
            if line.startswith('neighbor'):
                in_neighbor_block = True
                current_neighbor_ip = line.split()[1]
            
            # Capture description if within a neighbor block
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if find_value in description:  # Ensure 'find_value' is in description
                    return_value[current_neighbor_ip] = {'description': description}
            
            # Capture the import line if within a neighbor block
            elif line.startswith('import') and in_neighbor_block:
                current_import_line = line.split('"')[1]  # Extract the import policy name
                return_value[current_neighbor_ip]['import'] = current_import_line
            
            # Reset block flag on exit
            elif line == 'exit':
                in_neighbor_block = False

    except IndexError:
        print("# The target BGP group was not found in the file.")
        
    return return_value, cluster 

###############################################################

#--------------------------------------------------


# In[9]:


####### Create the new HUB policy with LL and NON LL b40 ips    ###################


def print_bgp_ll_neighbors(neighbors, start_key, old_import_policy, new_group, new_description, new_import_policy):
	global neighbor_ip
	print('#---------------------------------------------------------')
	print('#######-----      New BGP Configuration     -------######')
	print('#---------------------------------------------------------')
	print('/configure router bgp no keepalive')
	print('/configure router bgp no hold-time')
	print('/configure router bgp min-route-advertisement 1')
	print('/configure router bgp multi-path maximum-paths 16')
	print('/configure router bgp advertise-inactive')
	#print('/configure router bgp no bfd-enable')
	print('/configure router bgp rapid-withdrawal')
	
	print('##---------------------------------------------------------')        
	print('######-----       Delete Old BGP Group      -------######')
	print('##---------------------------------------------------------')
	print('/configure router bgp')
	print('    {} shutdown'.format(start_key))
	print('    no {}'.format(start_key))
	print('        exit all')
	print('/configure router policy-options')
	print ('            begin')
	print('    no policy-statement "{}"'.format(old_import_policy))
	print('    no policy-statement "{}"'.format(old_import_policy.replace("IMPORT", "EXPORT")))
	print('    no policy-statement "{}_LL"'.format(old_import_policy))
	print('    no policy-statement "{}_LL"'.format(old_import_policy.replace("IMPORT", "EXPORT")))
	print ('            commit')
	print ('exit all')
	print('')
	print('##---------------------------------------------------------')        
	print('######-----        Add New BGP Group        -------######')
	print('##---------------------------------------------------------')

	for neighbor_ip, details in neighbors.items():
		if 'LL' in details['import']:
			print('/configure router bgp')
			print('            group "{}_LL"'.format(new_group.split('"')[1]))
			print('                description "{}"'.format(new_description.replace("EBH AL", "LL EBH AL")))
			print('                family evpn label-ipv4')
			print('                type internal')
			print('                import "{}_LL"'.format(new_import_policy))
			print('                export "{}_LL"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
			print('                advertise-inactive')
			print('                bfd-enable')
			print('                aigp')
			print('                neighbor {}'.format(neighbor_ip))
			print('                    description "{}"'.format(details['description']))
			print('                    authentication-key "eNSEbgp"')
			print('                exit')
			print('            exit')
		if 'LL' not in details['import']:
			print('/configure router bgp')
			print('            {}'.format(new_group))
			print('                description "{}"'.format(new_description))
			print('                family evpn label-ipv4')
			print('                type internal')
			print('                import "{}"'.format(new_import_policy))
			print('                export "{}"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
			print('                advertise-inactive')
			print('                bfd-enable')
			print('                aigp')
			print('                neighbor {}'.format(neighbor_ip))
			print('                    description "{}"'.format(details['description']))
			print('                    authentication-key "eNSEbgp"')
			print('                exit')
			print('            exit')
		print('            no shutdown')
		print('        exit')
		print('    exit')
		print('exit all')


# In[10]:


def print_bgp_ll_neighbors_7705(neighbors, start_key, old_import_policy, new_group, new_description, new_import_policy):
	global neighbor_ip, ll_7705_details
	try:
		local_as = my_file_pd['config'][ my_file_pd.index[my_file_pd['config'].str.contains('local-as')].tolist()[0]].split()[1]
	except:
		print('# No Local-As found')

	print('#---------------------------------------------------------')
	print('#######-----      New BGP Configuration     -------######')
	print('#---------------------------------------------------------')
	print('/configure router bgp min-route-advertisement 1')
	#print('/configure router bgp multi-path maximum-paths 4')
	print('/configure router bgp no advertise-inactive')
	#print('/configure router bgp no bfd-enable')
	print('/configure router bgp no rapid-withdrawal')
	print('##---------------------------------------------------------')        
	print('######-----       Delete Old BGP Group      -------######')
	print('##---------------------------------------------------------')
	print('/configure router bgp')
	print('    {} shutdown'.format(start_key))
	print('    no {}'.format(start_key))
	print('        exit all')
	print('/configure router policy-options')
	print ('            begin')
	print('    no policy-statement "{}"'.format(old_import_policy))
	print('    no policy-statement "{}"'.format(old_import_policy.replace("IMPORT", "EXPORT")))
	#print('    no policy-statement "{}_LL"'.format(old_import_policy))
	#print('    no policy-statement "{}_LL"'.format(old_import_policy.replace("IMPORT", "EXPORT")))
	print ('   commit')
	print ('   exit')
	print ('exit all')
	print('')
	print('##---------------------------------------------------------')        
	print('######-----        Add New BGP Group        -------######')
	print('##---------------------------------------------------------')

	if '-01' in name:
		for neighbor_ip, ll_7705_details in neighbors.items():
			if 'B40-01' in ll_7705_details:
				print('/configure router bgp')
				print('            group "{}_LL"'.format(new_group.split('"')[1]))
				print('                description "{}"'.format(new_description.replace("RR-5-L3VPN_EBH", "RR-5-L3VPN_EBH_LL")))
				print('                family vpn-ipv4 vpn-ipv6 label-ipv4')
				#print('                type internal')
				print('                import "{}_LL"'.format(new_import_policy))
				print('                export "{}_LL"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
				print('                local-as {}'.format(local_as))
				print('                peer-as {}'.format(local_as))
				print('                advertise-inactive')
				print('                bfd-enable')
				print('                aigp')
				print('                neighbor {}'.format(neighbor_ip))
				print('                    description "{}"'.format(ll_7705_details))
				print('                    authentication-key "eNSEbgp"')
				print('                exit')
				print('            exit')
			if 'B40-02' in ll_7705_details:
				#print('/configure router bgp')
				print('            {}'.format(new_group))
				print('                description "{}"'.format(new_description))
				print('                family vpn-ipv4 vpn-ipv6 label-ipv4')
				#print('                type internal')
				print('                import "{}"'.format(new_import_policy))
				print('                export "{}"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
				print('                local-as {}'.format(local_as))
				print('                peer-as {}'.format(local_as))
				print('                advertise-inactive')
				print('                bfd-enable')
				print('                aigp')
				print('                neighbor {}'.format(neighbor_ip))
				print('                    description "{}"'.format(ll_7705_details))
				print('                    authentication-key "eNSEbgp"')
				print('                exit')
				print('            exit')
				print('            no shutdown')
				print('        exit')
				print('    exit')
				print('exit all')


# In[11]:


def extract_vprn_info(data):
    global vprn_value
    vprn_value = {}
    current_vprn = None  # To hold the current VPRN block (either 1 or 4)

    
    # Find the start index for the block
    group_start_idx = data[data['config'].str.contains('echo "Service')].index[0]
    # Slice the DataFrame starting from group_start_idx and search for the next 'echo ' string
    echo_slice = data.loc[group_start_idx:]
    group_end_idx = echo_slice[echo_slice['config'].str.contains('echo "Router')].index[0]
    #print(group_start_idx, group_end_idx)
    
    in_vprn_block = False
    current_interface = None
    for i in range(group_start_idx, group_end_idx):
        line = data.at[i, 'config'].strip()

        # Print the current line for debugging
        #print(f"Processing line {i}: {line}")
        # Start tracking VPRN block if it is 'vprn 1' or 'vprn 4'
        if line.startswith('vprn 1') or line.startswith('vprn 4'):
            current_vprn = line.split()[1]
            in_vprn_block = True
            #print(f"Entering VPRN block: {current_vprn}")
        # Capture interface name within a VPRN block
        elif line.startswith('interface') and in_vprn_block:
            current_interface = line.split('"')[1]  # Extract the interface name
            vprn_value[current_vprn] = vprn_value.get(current_vprn, {})
            vprn_value[current_vprn][current_interface] = {}
            #print(f"Captured interface: {current_interface} under VPRN {current_vprn}")
        # Capture the IPv6 address within a VPRN block and interface
        elif line.startswith('address') and in_vprn_block and current_interface:
            address = line.split()[1]  # Extract the address
            vprn_value[current_vprn][current_interface]['address'] = address
            #print(f"Captured address: {address} for interface {current_interface} under VPRN {current_vprn}")
        # Reset block flag when the 'exit' statement is found
        elif line == 'exit' and in_vprn_block:
            #print(f"Exiting VPRN block: {current_vprn}")
            current_interface = None
              # Close the VPRN block
    ##################################################################################################
    print ('')
    print ('#--------------------------------------------------')
    print ('# B40 post checks for pinging CSR interfaces on both B40-01 and 02"')
    print ('#--------------------------------------------------')
    print ('')
    for key, value in vprn_value.items():
        for sub_key, sub_value in value.items():
            if 'RAN' in sub_key:
        # Access the 'address' directly from the dictionary
                ip_add_1 = sub_value.get('address', '').split('/')[0]
                print('ping router-instance "RAN" {}'.format(ip_add_1))
    
            if 'CELL_MGMT' in sub_key:
        # Access the 'address' directly from the dictionary
                ip_add_2 = sub_value.get('address', '').split('/')[0]
                print('ping router-instance "CELL_MGMT" {}'.format(ip_add_2))


    #return vprn_value



# In[12]:


def extract_bgp_neighbors(data, start_key, end_key, find_value):
    global return_value, cluster
    return_value = {}
    cluster = None

    try:
        group_start_idx = data[data['config'].str.contains(start_key)].index[0]
        group_end_idx_candidates = data[data['config'].str.contains(r'group ')].index.tolist()
        group_end_idx = next((idx for idx in group_end_idx_candidates if idx > group_start_idx), len(data))

        #print(f"Processing group from {group_start_idx} to {group_end_idx}")

        in_neighbor_block = False
        current_neighbor_ip = None

        for i in range(group_start_idx, group_end_idx):
            line = data.at[i, 'config'].strip()

            # Capture the cluster value if it exists
            if line.startswith('cluster'):
                cluster = line.split()[1]  # Store the cluster IP
                #print(f"Cluster: {cluster}")
            if line.startswith('neighbor'):
                in_neighbor_block = True
                current_neighbor_ip = line.split()[1]
                #print(f"Neighbor IP: {current_neighbor_ip}")
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if find_value in description:  # Ensure 'find_value' is in description
                    return_value[current_neighbor_ip] = description
                    #print(f"Description: {description}")

            # Reset block flag on exit
            elif line == 'exit':
                in_neighbor_block = False

    except:
        print("# The target BGP group was not found in the file.")
    
    return return_value, cluster



def new_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy):
    print('#---------------------------------------------------------')        
    print('######-----       Delete Old BGP Group      -------######')
    print('#---------------------------------------------------------')
    print('/configure router bgp')
    print('    {} shutdown'.format(start_key))
    print('    no {}'.format(start_key))
    print('        exit all')
    print('/configure router policy-options')
    print ('            begin')
    print('    no policy-statement "{}"'.format(old_import_policy))
    print('    no policy-statement "{}"'.format(old_import_policy.replace("IMPORT", "EXPORT")))
    print ('            commit')
    print ('        exit')
    print ('exit all')
    print('')
    print('##---------------------------------------------------------')        
    print('######-----        Add New BGP Group        -------######')
    print('##---------------------------------------------------------')
    print('/configure router bgp')
    print('    {}'.format(new_group))
    print('                description "{}"'.format(new_description))
    print('                family evpn label-ipv4')
    print('                type internal')
    # Only print the cluster value if it exists (not None)
    if cluster_value is not None:
        print('                cluster {}'.format(cluster_value))
    print ('                import "{}"'.format(new_import_policy))
    print ('                export "{}"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
    print('                advertise-inactive')
    print('                bfd-enable')
    print('                aigp')

    # Loop through neighbors and descriptions in return_value
    for csr_neighbor_ip, description in return_value.items():
        print('                neighbor {}'.format(csr_neighbor_ip))
        print('                    description "{}"'.format(description))
        print('                    authentication-key "eNSEbgp"')
        print('                exit')

    print('exit all')
    print('#--------------------------------------------------')
################ include local-as 
##### for BGP group of 7705

def new_7705_bgp_group(neighbors, new_group, new_description,cluster_value, start_key, old_import_policy, new_import_policy):
    try:
        local_as = my_file_pd['config'][ my_file_pd.index[my_file_pd['config'].str.contains('local-as')].tolist()[0]].split()[1]
    except:
        print('# No Local-As found')

    print('##---------------------------------------------------------')        
    print('######-----       Delete Old BGP Group      -------######')
    print('##---------------------------------------------------------')
    print('/configure router bgp')
    print('    {} shutdown'.format(start_key))
    print('    no {}'.format(start_key))
    print('        exit')
    print('/configure router policy-options')
    print ('            begin')
    print('    no policy-statement "{}"'.format(old_import_policy))
    print('    no policy-statement "{}"'.format(old_import_policy.replace("IMPORT", "EXPORT")))
    print('        exit all')
    print ('            commit')
    print ('        exit')
    print ('exit all')
    print('')
    print('##---------------------------------------------------------')        
    print('######-----        Add New BGP Group        -------######')
    print('##---------------------------------------------------------')
    print('/configure router bgp')
    print('    {}'.format(new_group))
    print('                description "{}"'.format(new_description))
    print('                family vpn-ipv4 vpn-ipv6 label-ipv4')
    print('                type internal')

    # Only print the cluster value if it exists (not None)
    if cluster_value is not None:
        print('                cluster {}'.format(cluster_value))
    print ('                import "{}"'.format(new_import_policy))
    print ('                export "{}"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
    #print ('                local-as {}'.format(local_as))
    #print ('                peer-as {}'.format(local_as))
    #print('                advertise-inactive')
    print ('                bfd-enable')
    print ('                aigp')

    # Loop through neighbors and descriptions in return_value
    for csr_neighbor_ip, description in neighbors.items():
        print('                neighbor {}'.format(csr_neighbor_ip))
        print('                    description "{}"'.format(description))
        print('                    authentication-key "eNSEbgp"')
        print('                exit')

    print('exit all')
    print('#--------------------------------------------------')


# In[13]:


def bgp_rem_config():
    print('##---------------------------------------------------------')        
    print('######-----       BGP Group Changes         -------######')
    print('##---------------------------------------------------------')
    #print('/configure router bgp no family')
    print('/configure router bgp no bfd-enable')
    print('/configure router bgp add-paths')
    if '7250' in router_type:
        print('/configure router bgp error-handling update-fault-tolerance')
    print('##---------------------------------------------------------')


# In[14]:


######################## Groups for IXRE HUb - IXRE Spoke ###########################

# This group and policy will be applied for LL and non LL neighbor only.
def RR_5_ENSESR_EBH_LL(): # For policy  
	global extract_bgp_neighbors
	data = my_file_pd
	start_key = 'group "RR-5-ENSESR-CLIENT"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B40'
	new_group = 'group "RR-5-ENSESR_EBH"'
	new_description = 'Neighbor group for EVPN EBH AL' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_CSR-EBH' 

# Extract neighbors and cluster
	neighbors, cluster = extract_LL_bgp_neighbors(data, start_key, end_key, find_value)
	print_bgp_ll_neighbors(neighbors, start_key, old_import_policy, new_group, new_description, new_import_policy)


def RR_5_L3VPN_EBH_LL(): # 7705 HUB Facing AL
	data = my_file_pd
	start_key = 'group "RR-5-L3VPN-CLIENT"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-L3VPN-CLIENT'
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B40'
	new_group = 'group "RR-5-L3VPN_EBH"'
	new_description = 'Neighbor group for L3VPN EBH AL' 
	new_import_policy = 'IMPORT_RR-5-L3VPN_CSR-EBH'
# Extract neighbors and cluster
	neighbors, cluster = extract_bgp_neighbors(data, start_key, end_key, find_value)
	print_bgp_ll_neighbors_7705(neighbors, start_key, old_import_policy, new_group, new_description, new_import_policy)


###############   HUB to Spoke    ##################

def RR_5_ENSESR_CSR_SPOKE(): # IXRE spoke Facing IXRE HUB
	data = my_file_pd
	start_key = 'group "RR-5-ENSESR"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR'
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_SPOKE"'
	new_description = 'Neighbor group for EVPN AL' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_CSR-SPOKE'
# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)


##############    spoke to HUB    ###################

def RR_5_ENSESR_CSR(): # IXRE spoke Facing IXRE HUB
	data = my_file_pd
	start_key = 'group "RR-5-ENSESR-CLIENT"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_CSR"'
	new_description = 'Neighbor group for EVPN CSR' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_SPOKE-CSR'
# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)


def RR_5_L3VPN_CSR(): # IXRE spoke Facing IXRE HUB
	data = my_file_pd
	start_key = 'group "RR-5-L3VPN-CLIENT"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-L3VPN-CLIENT'
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4C'
	new_group = 'group "RR-5-L3VPN_CSR"'
	new_description = 'Neighbor group for L3VPN CSR' 
	new_import_policy = 'IMPORT_RR-5-L3VPN_SPOKE-CSR'
# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_7705_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)



# In[15]:


def L3VPN_CSR_SPOKE_7705(): # IXRE hub Facing 7705 Spoke
	data = my_file_pd
	start_key = 'group "RR-5-L3VPN"' #(Old group name)
	old_import_policy = 'IMPORT_RR_5_L3VPN'
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4C'
	new_group = 'group "RR-5-L3VPN_SPOKE"'
	new_description = 'Neighbor group for L3VPN SPOKE' 
	new_import_policy = 'IMPORT_RR-5-L3VPN_CSR-SPOKE'
# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_7705_bgp_group(neighbors,new_group, new_description,cluster_value, start_key, old_import_policy, new_import_policy)


# In[16]:


# Standalone IXRE policy config

def add_initial_policy():
    print ('#--------------------------------------------------')
    print ('# Change two security profile settings ...')
    print ('#--------------------------------------------------')
    print('')
    print('/configure system security profile "administrative" entry 80 action permit')
    print('/configure system security profile "administrative" entry 90 action permit')
    print('')
    print ('#--------------------------------------------------')
    print ('# New Spoke Policy Configuration')
    print ('#--------------------------------------------------')
    print('/configure router')
    print ('        policy-options')
    print ('            begin')
    print ('            prefix-list "PRFX_DEFAULT"')
    print ('                prefix 0.0.0.0/0 exact')
    print ('                prefix ::/0 exact')
    print ('            exit')
    print ('            prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print ('                prefix {}/32 exact'.format(system_ip))
    print ('            exit')
    print ('            commit')
    print ('exit all')


    
def policy_RR_5_ENSESR_CSR_EBH():
    print ('#--------------------------------------------------')
    print('/configure router')
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_CSR-EBH"')
    print ('                description "EXPORT ROUTES TO THE EBH ACCESS LEAF"')
    print ('                entry 5')
    print ('                description "DROP DEFAULT ROUTE"')
    print ('                    from')
    print ('                        prefix-list "PRFX_DEFAULT"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
    print ('                entry 10')
    print ('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print ('                    from')
    print ('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 20')
    print ('                    description "PROPAGATE CONNECTED ROUTES"')
    print ('                    from')
    print ('                        protocol direct')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol evpn-ifl')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                entry 30')
    print ('                    description "PROPAGATE BGP LABELS"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 40')
    print ('                    description "PROPAGATE EVPN ROUTES"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_CSR-EBH"')
    print ('                description "IMPORT ROUTES FROM EBH ACCESS LEAF"')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')
    print ('exit all')

def policy_RR_5_ENSESR_CSR_EBH_LL():
    print('/configure router')
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_CSR-EBH_LL"')
    print ('                description "EXPORT ROUTES TO THE LL EBH ACCESS LEAF"')
    print ('                entry 5')
    print ('                   description "DROP DEFAULT ROUTE"')
    print ('                    from')
    print ('                        prefix-list "PRFX_DEFAULT"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
    print ('                entry 10')
    print ('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print ('                    from')
    print ('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        local-preference 500')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 20')
    print ('                    description "PROPAGATE CONNECTED ROUTES"')
    print ('                    from')
    print ('                        protocol direct')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol evpn-ifl')
    print ('                    exit')
    print ('                    action accept')
    print ('                        local-preference 500')
    print ('                    exit')
    print ('                exit')
    print ('                entry 30')
    print ('                    description "PROPAGATE BGP LABELS"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        local-preference 500')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 40')
    print ('                    description "PROPAGATE EVPN ROUTES"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                        local-preference 500')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_CSR-EBH_LL"')
    print ('                description "IMPORT ROUTES FROM THE LL HUB ACCESS LEAF"')
    print ('                default-action accept')
    print ('                    local-preference 500')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')
    print ('exit all')


# Spoke IXRE only facing IXRE HUB
def policy_RR_5_ENSESR_SPOKE_CSR():
    print ('#--------------------------------------------------')
    print('/configure router')
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_SPOKE-CSR"')
    print ('                description "EXPORT ROUTES TO A CSR"')
    print ('                entry 5')
    print ('                    description "DROP DEFAULT ROUTE"')
    print ('                    from')
    print ('                        prefix-list "PRFX_DEFAULT"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
    print ('                entry 10')
    print ('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print ('                    from')
    print ('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 20')
    print ('                    description "PROPAGATE CONNECTED ROUTES"')
    print ('                    from')
    print ('                        protocol direct')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol evpn-ifl')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                entry 30')
    print ('                    description "PROPAGATE BGP LABELS"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 40')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_SPOKE-CSR"')
    print ('                description "IMPORT ROUTES FROM A CSR"')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')
    print ('exit all')



# HUB IXRE policy facing IXRE Spoke
def policy_RR_5_ENSESR_CSR_SPOKE():
    print ('#--------------------------------------------------')
    print ('# New HUb to Spoke Policy Configuration')
    print ('#--------------------------------------------------')
    print('/configure router')
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_CSR-SPOKE"')
    print ('                description "EXPORT ROUTES TO A SPOKE"')
    print ('                entry 10')
    print ('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print ('                    from')
    print ('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 20')
    print ('                    description "PROPAGATE CONNECTED ROUTES"')
    print ('                    from')
    print ('                        protocol direct')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol evpn-ifl')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                entry 30')
    print ('                    description "PROPAGATE BGP LABELS"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 40')
    print ('                    description "PROPAGATE EVPN ROUTES"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_CSR-SPOKE"')
    print ('                description "IMPORT ROUTES FROM A SPOKE"')
    print ('                entry 5')
    print ('                    description "DROP DEFAULT ROUTE"')
    print ('                    from')
    print ('                        prefix-list "PRFX_DEFAULT"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
    print ('                entry 10')
    print ('                    description "IMPORT BGP LABELS"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 20')
    print ('                    description "IMPORT EVPN ROUTES"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')
    print ('exit all')
    print ('#--------------------------------------------------')
    
def csr_osw_l3vpn_policy(my_file_pd):
    try:
        csr_osw = my_file_pd['config'].index[my_file_pd['config'].str.contains('EXPORT_RR-5-ENSESR_CSR-OSW_L3VPN"')].tolist()
        if bool(csr_osw):
            print ('#--------------------------------------------------')
            print ('# Modify Policy Configuration for CSR-OSW')
            print ('#--------------------------------------------------')
            print('/configure router')
            print ('        policy-options')
            print ('            begin')
            print ('                policy-statement "EXPORT_RR-5-ENSESR_CSR-OSW_L3VPN"')
            print ('                entry 10')
            print ('                    from')
            print ('                        no prefix-list "Default-Routes"')
            print ('                        prefix-list "PRFX_DEFAULT"')
            print ('                    exit')
            print ('                exit')
            print ('            exit')
            print ('            policy-statement "EXPORT_RR-5-ENSESR_CSR-OSW_L3VPN_WSN"')
            print ('                entry 10')
            print ('                    from')
            print ('                        no prefix-list "Default-Routes"')
            print ('                        prefix-list "PRFX_DEFAULT"')
            print ('                    exit')
            print ('                exit')
            print ('            exit all')
    except():
        print("")
    


# In[17]:


#######################    7705 policies    ###############################

def policy_RR_5_L3VPN_CSR_EBH():
    print ('#--------------------------------------------------')
    print('/configure router')
    print ('        policy-options')
    print ('            begin')
    print('            policy-statement "EXPORT_RR-5-L3VPN_CSR-EBH"')
    print('                description "EXPORT ROUTES TO EBH ACCESS LEAF"')
    print('                entry 5')
    print('                    description "DROP DEFAULT ROUTE"')
    print('                    from')
    print('                        prefix-list "PRFX_DEFAULT"')
    print('                    exit')
    print('                    action reject')
    print('                exit')
    print('                entry 10')
    print('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print('                    from')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "PROPAGATE CONNECTED ROUTES"')
    print('                    from')
    print('                        protocol direct')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-vpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                entry 30')
    print('                    description "PROPAGATE BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 40')
    print('                    description "PROPAGATE VPN ROUTES"')
    print('                    from')
    print('                        family vpn-ipv4 vpn-ipv6')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                default-action reject')
    print('            exit')
    print('            policy-statement "IMPORT_RR-5-L3VPN_CSR-EBH"')
    print('                description "IMPORT ROUTES FROM EBH ACCESS LEAF"')
    print('                default-action accept')
    print('                exit                  ')
    print('            exit')
    print ('            commit')
    print ('        exit')
    print ('exit all')


def policy_RR_5_L3VPN_CSR_EBH_LL():
    print ('#--------------------------------------------------')
    print('/configure router')
    print ('        policy-options')
    print ('            begin')
    print('            policy-statement "EXPORT_RR-5-L3VPN_CSR-EBH_LL"')
    print('                description "EXPORT ROUTES TO LL EBH ACCESS LEAF"')
    print('                entry 5')
    print('                    description "DROP DEFAULT ROUTE"')
    print('                    from')
    print('                        prefix-list "PRFX_DEFAULT"')
    print('                    exit')
    print('                    action reject')
    print('                exit')
    print('                entry 10')
    print('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print('                    from')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        local-preference 500')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "PROPAGATE CONNECTED ROUTES"')
    print('                    from')
    print('                        protocol direct')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-vpn')
    print('                    exit')
    print('                    action accept')
    print('                        local-preference 500')
    print('                    exit')
    print('                exit')
    print('                entry 30')
    print('                    description "PROPAGATE BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        local-preference 500')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 40')
    print('                    description "PROPAGATE VPN ROUTES"')
    print('                    from')
    print('                        family vpn-ipv4 vpn-ipv6')
    print('                    exit')
    print('                    action accept')
    print('                        local-preference 500')
    print('                    exit')
    print('                exit')
    print('                default-action reject')
    print('            exit')
    print('            policy-statement "IMPORT_RR-5-L3VPN_CSR-EBH_LL"')
    print('                description "IMPORT ROUTES FROM LL EBH ACCESS LEAF"')
    print('                default-action accept')
    print('                    local-preference 500')
    print('                exit')
    print('            exit')
    print ('            commit')
    print ('        exit')
    print ('exit all')

def policy_RR_5_L3VPN_CSR_SPOKE():
    print ('#--------------------------------------------------')
    print('/configure router')
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-L3VPN_CSR-SPOKE"')
    print ('                description "EXPORT ROUTES TO A SPOKE"')
    print ('                entry 10')
    print ('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print ('                    from')
    print ('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 20')
    print ('                    description "PROPAGATE CONNECTED ROUTES"')
    print ('                    from')
    print ('                        protocol direct')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-vpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                entry 30')
    print ('                    description "PROPAGATE BGP LABELS"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 40')
    print ('                    description "PROPAGATE VPN ROUTES"')
    print ('                    from')
    print ('                        family vpn-ipv4 vpn-ipv6')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-L3VPN_CSR-SPOKE"')
    print ('                description "IMPORT ROUTES FROM A SPOKE"')
    print ('                entry 5')
    print ('                    description "DROP DEFAULT ROUTE"')
    print ('                    from')
    print ('                        prefix-list "PRFX_DEFAULT"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
    print ('                entry 10')
    print ('                    description "IMPORT BGP LABELS"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 20')
    print ('                    description "IMPORT VPN ROUTES"')
    print ('                    from')
    print ('                        family vpn-ipv4 vpn-ipv6')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('            exit')
    print ('            commit')
    print ('        exit')
    print ('exit all')

def policy_RR_5_L3VPN_SPOKE_CSR():
    print ('#--------------------------------------------------')
    print('/configure router')
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-L3VPN_SPOKE-CSR"')
    print ('                description "EXPORT ROUTES TO A CSR"')
    print ('                entry 5')
    print ('                    description "DROP DEFAULT ROUTE"')
    print ('                    from')
    print ('                        prefix-list "PRFX_DEFAULT"')
    print ('                    exit')
    print ('                    action reject')
    print ('                exit')
    print ('                entry 10')
    print ('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print ('                    from')
    print ('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 20')
    print ('                    description "PROPAGATE CONNECTED ROUTES"')
    print ('                    from')
    print ('                        protocol direct')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-vpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                entry 30')
    print ('                    description "PROPAGATE BGP LABELS"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 40')
    print ('                    description "PROPAGATE VPN ROUTES"')
    print ('                    from')
    print ('                        family vpn-ipv4 vpn-ipv6')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action reject')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-L3VPN_SPOKE-CSR"')
    print ('                description "IMPORT ROUTES FROM A CSR"')
    print ('                default-action accept')
    print ('            exit')
    print ('            commit')
    print ('        exit')
    print ('exit all')

####################################################################


# In[18]:


# B40 group change and check interface to 1000000

def b40_01_changes_ixre(system_ip, name):
    print ('###Remove neighbor from 121 bgp group ')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------')
    print ('# Check for the routers interface metric under ISIS 5"')
    print ('#--------------------------------------------------')
    print ('admin display-config | match "{}" context all'.format(name))
    print ('/show router isis 5 interface | match "<site interface>"')
    #print ('/configure router isis 5 interface " level 1 metric 1000000
    print ('If the above interface level 1 metric is not 1000000 then change it to 1000000')


def b40_02_changes_ixre(system_ip, name):
    print ('###Remove neighbor from 121 bgp group ')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------')
    print ('# Check for the routers interface metric under ISIS 5"')
    print ('#--------------------------------------------------')
    print ('admin display-config | match "{}" context all'.format(name))
    print ('/show router isis 5 interface | match "<site interface>"')
    print ('If the interface level 1 metric is not 1000000 then change it to 1000000')


# B40 group change and check interface to 1000000

def b40_01_rollback_ixre(system_ip, name):
    print ('')
    print ('')
    print ('')
    print ('###################################################')
    print ('#     ROLLBACK FOR B40-01     "')
    print ('#--------------------------------------------------')
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_CSR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------')


def b40_02_rollback_ixre(system_ip, name):
    print ('')
    print ('')
    print ('')
    print ('###################################################')
    print ('#     ROLLBACK FOR B40-02     "')
    print ('#--------------------------------------------------')
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_CSR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------')
    print ('# Check for the routers interface metric under ISIS 5"')
    print ('#--------------------------------------------------')
    print ('admin display-config | match "{}" context all'.format(name))
    print ('/show router isis 5 interface | match "<site interface>"')
    print ('If the interface level 1 metric is not 1000000 then change it to 1000000')


# In[19]:


def del_policy_ixre():
    print('#--------------------------------------------------')
    print('## Cleaning LLD 1.2.1 prefix lists and communities ... ')
    print('#--------------------------------------------------')
    print('')
    print('/configure router policy-options')
    print('  begin')
    print('    no prefix-list "Default-Routes"')
    print('    no prefix-list "PRFX_LOCAL_SYSTEM_ADDRESS"')
    print('  commit')
    print('exit all')
    if '7250' in router_type:
        print ('#--------------------------------------------------')
        print ('# Change port 1/1/24 port (IXRE-Management-Port)speed to 1000 ...')
        print ('#--------------------------------------------------')
        print('/configure port 1/1/24 ethernet speed 1000')
        print('')
    print ('#--------------------------------------------------')
    print ('# Re-enable two security profile settings ...')
    print ('#--------------------------------------------------')
    print('')
    print('/configure system security profile "administrative" entry 80 action deny')
    print('/configure system security profile "administrative" entry 90 action deny')
    print('/bof save')
    print('/admin save')
    print('/admin display-config')


# In[20]:


def pre_checks():
    print('########### Following info is Just to verify the interface and all system info ############')
    print('# System Name: {}", "system ip: {}" , " Router Type: {}"'.format(name, system_ip, router_type))
    print('##############################################################')
    print('')
    print('###-----      create system rollback     -------###')
    print('')
    print('/show system rollback')
    print('/admin rollback save comment "Pre-update Checkpoint"')
    print('')
    print('###-----     Precheck commands to run before start of work -----###')
    print('')
    print('\environment no more ')
    print('\environment time-stamp ')
    print('\admin display-config ')
    print('\show version ')
    print('\show bof ')
    print('\show chassis ')
    print('\show system memory-pools ')
    print('\show card ')
    print('\show mda ')
    print('\show port ')
    print('\show port description ')
    print('\show router status ')
    print('\show router interface ')
    print('\show router route-table summary ipv6 ')
    print('\show router route-table ')
    print('\show router route-table ipv6 ')
    print('\show router isis 5 adjacency ')
    print('\show router isis 5 routes ')
    print('\show router isis 5 interface ')
    print('\show router bgp summary ')
    print('\show router bgp neighbor ')
    print('\show router bgp group ')
    print('\show router bgp routes label-ipv4 ')
    print('\show router bgp routes evpn  ip-prefix ')
    print('\show router bgp routes evpn ip6-prefix')
    print('\show service service-using ')
    print('\show service id 1 base ')
    print('\show service id 100 base ')
    print('\show service id 4 base ')
    print('\show service id 400 base ')
    print('\show router 1 status ')
    print('\show router tunnel-table | match 172.31. ')
    print('\show router 1 interface ')
    print('\show router 1 route-table ')
    print('\show router 1 route-table ipv6')
    print('\show service id  bgp-evpn ')
    print('\show router 4 status ')
    print('\show router 4 interface ')
    print('\show router 4 route-table ')
    print('\show router 4 route-table ipv6')
    print('\show log log-id 100 ')
    print('\show log log-id 99')
    print('\show system information')
    print('\show service sap-using')
    print('\show time')
    print('\show system ptp port')
    print('\show system sync-if-timing')

# Post check ping check script / 
def post_checks():
    print ('')
    print ('#--------------------------------------------------')
    print ('# IXR/7705 router post checks "')
    print ('#--------------------------------------------------')
    print ('show service sap-using')
    print ('show port A/gnss')
    print ('show system ptp port')
    print ('show router 1 interface')
    print ('show router 4 interface')
    print('show router isis 5 interface ')
    print ('show router policy')
    print ('show router bgp summary')
    print ('')
    print ('#--------------------------------------------------')
    print ('# B40 router post checks "')
    print ('#--------------------------------------------------')
    print('show router bgp summary | match {}'.format(name))
    print ('show router bgp summary | match B4C con all')
    print ('show router bgp summ group "RR-5-ENSESR" | match B4C post-lines 2 ')
    print ('show router bgp summ group "RR-5-ENSESR_CSR"  | match B4C post-lines 2 ')
    print ('show router bgp group "RR-5-ENSESR" | match B4C pre-lines 1 ')
    print ('show router bgp group "RR-5-ENSESR_CSR"  | match B4C pre-lines 1 ')


# In[21]:


# B40 group change and check interface to 1000000

def b40_01_changes_ixre(system_ip, name):
    print ('###Remove neighbor from 121 bgp group ONLY after adding the bgp on B40-01 and 02')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------')
    print ('# Check for the routers interface metric under ISIS 5"')
    print ('#--------------------------------------------------')
    print ('admin display-config | match "{}" context all'.format(name))
    print ('/show router isis 5 interface | match "<site interface>"')
    #print ('/configure router isis 5 interface " level 1 metric 1000000
    print ('If the above interface level 1 metric is not 1000000 then change it to 1000000')


def b40_02_changes_ixre(system_ip, name):
    print ('###Remove neighbor from 121 bgp group after you have brought up 135 BGP neigh on B40-01 and 02')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR_CSR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------')
    print ('# Check for the routers interface metric under ISIS 5"')
    print ('#--------------------------------------------------')
    print ('admin display-config | match "{}" context all'.format(name))
    print ('/show router isis 5 interface | match "<site interface>"')
    print ('If the interface level 1 metric is not 1000000 then change it to 1000000')



############################################################################################################################


# In[22]:


def b40_bgp_conf(folder):
    met_int_b4c, met_int_b40 = metric_nni(my_file_pd)
    for interface_desc, description in met_int_b40.items():
        #print(interface_desc, description)
        if 'B40' in description:
            # B40-01 changes in a new file #################################
            sys.stdout = open(folder + '/' + name +'_B40-01.txt','w')
            b40_01_changes_ixre(system_ip, name)
            b40_01_rollback_ixre(system_ip, name)
            # B40-02 changes in a new file #################################
            sys.stdout = open(folder + '/' + name +'_B40-02.txt','w')
            b40_02_changes_ixre(system_ip, name)
            b40_02_rollback_ixre(system_ip, name)


# In[23]:


import os
import logging

# Set up logging
logging.basicConfig(filename='error_log.txt', level=logging.ERROR, 
                    format='%(asctime)s:%(levelname)s:%(message)s')

def main():
    global items,folder

    scan_file()
    all_files()
    cwd = os.getcwd()  # Save the current directory to return back after each iteration

    for items in path:
        try:
            create_pd()
            # print(name)
            # IXRE policies for HUB, spoke
            csr_ixre_grp = my_file_pd.index[my_file_pd['config'].str.contains('group "RR-5-ENSESR-CLIENT"')].tolist()  # to B40 or AL or HUB
            csr_ixre_al = my_file_pd.index[my_file_pd['config'].str.contains('import "IMPORT_RR-5-ENSESR-CLIENT"')].tolist()  # to B40 or AL or HUB
            csr_ixre_al_ll = my_file_pd['config'].index[my_file_pd['config'].str.fullmatch('import "IMPORT_RR-5-ENSESR-CLIENT_LL"')].tolist()
            
            csr_ixre_spoke = my_file_pd.index[my_file_pd['config'].str.contains('group "RR-5-ENSESR"')].tolist()  # configured on DRAN IXR-E if it has Spoke IXR-E
            
            # IXRE policies for HUB, spoke IXRE facing 7705 with L3VPN
            csr_ixre_7705_grp = my_file_pd.index[my_file_pd['config'].str.contains('group "RR-5-L3VPN-CLIENT"')].tolist()  # to B40 or AL or HUB with 7705 as spoke
            csr_7705_al = my_file_pd['config'].index[my_file_pd['config'].str.contains('B40')].tolist()

            csr_ixre_7705_spoke = my_file_pd.index[my_file_pd['config'].str.contains('group "RR-5-L3VPN"')].tolist()  # to the spoke from HUB with 7705
            
            if not os.path.isdir(name):
                os.mkdir(name)
            os.chdir(name)
            folder = os.getcwd()

            # IXRE config changes based on policies
            sys.stdout = open(folder + '/' + name + '_LLD135.cfg', 'w')
            pre_checks()
            metric_interface_nni()
            bgp_rem_config()
            add_initial_policy()
#---------------------------------------      EVPN      #-----------------------------------------------------------#

            if bool(csr_ixre_grp) and bool(csr_ixre_al) and bool(csr_ixre_al_ll):
                policy_RR_5_ENSESR_CSR_EBH()
                policy_RR_5_ENSESR_CSR_EBH_LL()
                RR_5_ENSESR_EBH_LL() # This is a HUB policy for LL and non LL neighbors
                                
            if bool(csr_ixre_spoke):
                policy_RR_5_ENSESR_CSR_SPOKE()
                RR_5_ENSESR_CSR_SPOKE() # This is from hub to spoke
                #print('# This is to spoke')
#----------------------------------------    L3VPN     #------------------------------------------------------------#
            if bool(csr_ixre_7705_spoke):
                policy_RR_5_L3VPN_CSR_SPOKE()
                L3VPN_CSR_SPOKE_7705()
#------------------------------------    SPOKE TO HUB     #----------------------------------------------------------------#
            if bool(csr_ixre_grp) and not bool(csr_ixre_al_ll):
                policy_RR_5_ENSESR_SPOKE_CSR()
                RR_5_ENSESR_CSR() # On Spoke to evpn hub facing policy

            if bool(csr_ixre_7705_grp) and bool(csr_7705_al):
                print(bool(csr_ixre_7705_grp), bool(csr_7705_al))
                policy_RR_5_L3VPN_CSR_EBH()
                policy_RR_5_L3VPN_CSR_EBH_LL()
                RR_5_L3VPN_EBH_LL() # This is a L3VPN HUB policy for LL and non LL neighbors for any 7705 downstream

            if bool(csr_ixre_7705_grp) and not bool(csr_7705_al):
                policy_RR_5_L3VPN_SPOKE_CSR()
                RR_5_L3VPN_CSR() # On Spoke to l3vpn hub facing policy

            del_policy_ixre()
            b40_bgp_conf(folder)

#-----------------------------------    BOF and post checks     #----------------------------------------------------------#
            sys.stdout = open(folder + '/' + name + '_bof.cfg', 'w')
            bof_data()
            create_bof(old_statics)

            sys.stdout = open(folder + '/' + name + '_Post_Checks.txt', 'w')
            post_checks()
            extract_vprn_info(my_file_pd)

            os.chdir(cwd)  # up directory

        except Exception as e:
            # Log the error
            #print(f"Error processing file {items}: {e}")
            #logging.error(f"Error processing file {items}: {e}")
            continue  # skip to  next item in the for loop




# In[24]:


if __name__ == "__main__":
    if check_for_update():
        restart_script()
    else:
        main()


# In[ ]:





# In[ ]:




