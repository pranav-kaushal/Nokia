#!/usr/bin/env python
# coding: utf-8

# In[1]:


# Import required libraries
# Version 1.10

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
GITHUB_FILE_URL = "https://raw.githubusercontent.com/pranav-kaushal/Nokia/refs/heads/main/Ring/Ring_121to135LLD.py"
cwd = os.getcwd()
LOCAL_FILE_PATH  = os.path.join(cwd, 'Ring_121to135LLD.py') # Path for the current script file
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


def b40_name_get():
    global b40_name
    
    import_string = 'import "IMPORT_RR-5-ENSESR-CLIENT"'
    import_index = my_file_pd.index[my_file_pd['config'] == import_string].tolist()
    
    # Step 2: If the import string is found, iterate the next 10 rows to look for 'description' containing 'B40'
    b40_name = []
    description_pattern = re.compile(r'description.*B40', re.IGNORECASE)
    
    if import_index:
        for idx in import_index:
            # Check the next 10 lines after the 'import' line
            for i in range(idx + 1, min(idx + 8, len(my_file_pd))):
                if description_pattern.search(my_file_pd.loc[i, 'config']):
                    b40_name.append({
                        #'import': my_file_pd.loc[idx, 'config'],
                        'description': my_file_pd.loc[i, 'config']
                    })
                    break
    b40_name = my_file_pd.loc[i, 'config']
    b40_name = b40_name[-15:-1]
    return b40_name


# In[7]:


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


# In[8]:


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
    #return vprn_value



# In[9]:


# Get the interfaces for which the metric has to be changed.
def metric_int(data):
    global metric_interface
    metric_interface = {}
    try:
        # Find the start of the group "RR-5-ENSESR"
        group_start_idx = data[data['config'].str.fullmatch('router Base')].index[0] #Find the index of the line containing 'group "RR-5-ENSESR"'.
        
        # Loop through the subsequent lines to find neighbors and descriptions
        in_neighbor_block = False #Use a flag in_neighbor_block to track if we are within a neighbor block.
        interface_desc = None
    
        for i in range(group_start_idx + 1, len(data)):
            line = data.at[i, 'config'].strip()
            
            if line.startswith('interface'):
                in_neighbor_block = True
                interface_desc = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if 'B40' in description:  # Check if description does not contain "B40"
                    metric_interface[interface_desc] = description
                in_neighbor_block = False
            elif line == 'exit':
                in_neighbor_block = False
    except IndexError:
        print("No B40 interface was found")
    #for interface_desc, description in metric_interface.items():
     #   print('/configure router isis 5 {} level 1 metric 1000000'.format(interface_desc))
    return metric_interface


# In[10]:


# This is only for the node which is connected to B40, it will check for CSR connected to it and the spokes in the ring.
# So only looking for group "RR-5-ENSESR.

def extract_neighbors(data, start_key):
    global spoke_bgp_neighbors
    global csr_bgp_neighbors
    spoke_bgp_neighbors = {}
    csr_bgp_neighbors = {}
    cluster = None
    
    try:
        # Find the start and end of the group "RR-5-ENSESR"
        group_start_idx = data[data['config'].str.contains(start_key)].index[0]
        group_end_idx_candidates = data[data['config'].str.contains(r'group ')].index.tolist()
        group_end_idx = next((idx for idx in group_end_idx_candidates if idx > group_start_idx), len(data))
        
        in_neighbor_block = False
        current_neighbor_ip = None
        
        for i in range(group_start_idx + 1, group_end_idx):
            line = data.at[i, 'config'].strip()
            if line.startswith('cluster'):
                cluster = line.split()[1]  # Store the cluster IP
            if line.startswith('neighbor'):
                in_neighbor_block = True
                current_neighbor_ip = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if 'B40' not in description and 'Spoke' in description: # Check if there is no B40 but spoke in description
                    spoke_bgp_neighbors[current_neighbor_ip] = description
                elif 'B40' not in description and 'Spoke' not in description: # Check if there is no B40 and no spoke in description
                    csr_bgp_neighbors[current_neighbor_ip] = description
                in_neighbor_block = False
            elif line == 'exit':
                in_neighbor_block = False
    except IndexError:
        print("# The target group was not found in the file.")
    
    return spoke_bgp_neighbors, csr_bgp_neighbors, cluster

def add_spoke_csr_bgp_neighbors(start_key,old_import_policy,new_group, new_description,new_import_policy, neighbors, cluster):
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
    if cluster is not None:
        print('                cluster {}'.format(cluster))
    print('                import "{}"'.format(new_import_policy))
    print('                export "{}"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
    print('                bfd-enable')
    print('                aigp')
    for neighbor_ip, description in neighbors.items():
        print('                neighbor {}'.format(neighbor_ip))
        print('                    description "{}"'.format(description))
        print('                    authentication-key "eNSEbgp"')
        print('                exit')
    print('exit all')
    print('#--------------------------------------------------')     


# Print all the spoke nodes under Old group "RR-5-ENSESR"
def RR_5_ENSESR_IRRW_SPOKE():  #(tested)
    start_key = 'group "RR-5-ENSESR"' #(Old group name)
    old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
    find_value = 'B4C'
    new_group = 'group "RR-5-ENSESR_SPOKE"'
    new_description = 'Neighbor group for EVPN SPOKE' 
    new_import_policy = 'IMPORT_RR-5-ENSESR_IRRW-SPOKE' 
    # Extract neighbors and cluster
    neighbors, csr_bgp_neighbors, cluster = extract_neighbors(my_file_pd, start_key)
    add_spoke_csr_bgp_neighbors(start_key,old_import_policy,new_group, new_description,new_import_policy, neighbors, cluster)


def RR_5_ENSESR_IRRW_CSR():  #(tested)
    start_key = 'group "RR-5-ENSESR"' #(Old group name)
    old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
    find_value = 'B4C'
    new_group = 'group "RR-5-ENSESR_CSR"'
    new_description = 'Neighbor group for EVPN CSR' 
    new_import_policy = 'IMPORT_RR-5-ENSESR_IRRW-CSR' 
    # Extract neighbors and cluster
    csr_bgp_neighbors, neighbors, cluster = extract_neighbors(my_file_pd, start_key)  
    add_spoke_csr_bgp_neighbors(start_key,old_import_policy,new_group, new_description,new_import_policy, neighbors, cluster)


#East Spokes

# Print all the spoke nodes under Old group "RR-5-ENSESR"
def RR_5_ENSESR_IRRE_SPOKE():
    start_key = 'group "RR-5-ENSESR"' #(Old group name)
    old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
    find_value = 'B4C'
    new_group = 'group "RR-5-ENSESR_SPOKE"'
    new_description = 'Neighbor group for EVPN SPOKE' 
    new_import_policy = 'IMPORT_RR-5-ENSESR_IRRE-SPOKE' 
    # Extract neighbors and cluster
    neighbors, csr_bgp_neighbors, cluster = extract_neighbors(my_file_pd, start_key)
    add_spoke_csr_bgp_neighbors(start_key,old_import_policy,new_group, new_description,new_import_policy, neighbors, cluster)


def RR_5_ENSESR_IRRE_CSR():
    start_key = 'group "RR-5-ENSESR"' #(Old group name)
    old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
    find_value = 'B4C'
    new_group = 'group "RR-5-ENSESR_CSR"'
    new_description = 'Neighbor group for EVPN CSR' 
    new_import_policy = 'IMPORT_RR-5-ENSESR_IRRE-CSR' 
    # Extract neighbors and cluster
    spoke_bgp_neighbors, neighbors, cluster = extract_neighbors(my_file_pd, start_key)
    add_spoke_csr_bgp_neighbors(start_key,old_import_policy,new_group, new_description,new_import_policy, neighbors, cluster) # csr neighbor



# In[11]:


def extract_spoke_neighbors(data, start_key, find_value):
    global csr_sp_neighbors
    csr_sp_neighbors = {}
    cluster = None
    try:
        # Find the start and end indices for the group
        group_start_idx = data[data['config'].str.contains(start_key)].index[0]
        group_end_idx_candidates = data[data['config'].str.contains(r'group ')].index.tolist()
        group_end_idx = next((idx for idx in group_end_idx_candidates if idx > group_start_idx), len(data))
        
        in_neighbor_block = False
        current_neighbor_ip = None
        
        for i in range(group_start_idx + 1, group_end_idx):
            line = data.at[i, 'config'].strip()
            if line.startswith('cluster'):
                cluster = line.split()[1]  # get ip
            if line.startswith('neighbor'):
                in_neighbor_block = True
                current_neighbor_ip = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if find_value in description:
                    csr_sp_neighbors[current_neighbor_ip] = description
                    #print(f"Neighbor added: {current_neighbor_ip} with description {description}")  # Debug: Print added neighbor
                in_neighbor_block = False 
            elif line == 'exit':
                in_neighbor_block = False
                #print("Exiting neighbor block")  # Debug: Print exit from neighbor block
                
    except IndexError:
        print(f"# The target group '{start_key}' was not found in the file.")
    return csr_sp_neighbors, cluster

def new_spoke_bgp_group(new_group, new_description, csr_sp_neighbors ,cluster, start_key, old_import_policy, new_import_policy): # This group and policies are for the spoke only
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
    if cluster is not None:
        print('                cluster {}'.format(cluster))
    print('                import "{}"'.format(new_import_policy))
    print('                export "{}"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
    print('                bfd-enable')
    print('                aigp')
    #print(csr_sp_neighbors.items())
    for neighbor_ip, description in csr_sp_neighbors.items():
        print('                neighbor {}'.format(neighbor_ip))
        print('                    description "{}"'.format(description))
        print('                    authentication-key "eNSEbgp"')
        print('                exit')
    print('exit all')
    print('#--------------------------------------------------')
    
def rr_5_csr_ring_spoke(): # This group and policies are for the spoke only
	start_key = 'group "RR-5-ENSESR"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_SPOKE"'
	new_description = 'Neighbor group for EVPN CSR' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_CSR-SPOKE' 
    # Extract neighbors and cluster
	csr_sp_neighbors, cluster = extract_ring_neighbors(my_file_pd, start_key, find_value)
	new_spoke_bgp_group(new_group, new_description, csr_sp_neighbors ,cluster, start_key, old_import_policy, new_import_policy)


def rr_5_ensesr_IRR(): # This group and policies are for the spoke only 
	start_key = 'group "RR-5-ENSESR-CLIENT"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_IRR"'
	new_description = 'Neighbor group for EVPN IRR' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_CSR-IRR' 
    # Extract neighbors and cluster
	csr_sp_neighbors, cluster = extract_spoke_neighbors(my_file_pd, start_key,find_value)
	#print(csr_sp_neighbors)
	new_spoke_bgp_group(new_group, new_description, csr_sp_neighbors ,cluster, start_key, old_import_policy, new_import_policy)

def rr_5_ensesr_spoke(): # This group and policies are for the spoke only 
	start_key = 'group "RR-5-ENSESR-CLIENT"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_CSR"'
	new_description = 'Neighbor group for EVPN CSR' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_SPOKE-CSR' 
    # Extract neighbors and cluster
	csr_sp_neighbors, cluster = extract_spoke_neighbors(my_file_pd, start_key,find_value)
	#print(csr_sp_neighbors)
	new_spoke_bgp_group(new_group, new_description, csr_sp_neighbors ,cluster, start_key, old_import_policy, new_import_policy)


# In[12]:


# --- This is non B40 ring router
def extract_ring_neighbors(data, start_key, find_value):
    global ring_neighbors
    # Initialize a dictionary to store neighbors and their descriptions
    ring_neighbors = {}
    cluster = None
    try:
        group_start_idx = data[data['config'].str.contains(start_key)].index[0]
        group_end_idx_candidates = data[data['config'].str.contains(r'group ')].index.tolist()
        group_end_idx = next((idx for idx in group_end_idx_candidates if idx > group_start_idx), len(data))

        in_neighbor_block = False #Use a flag in_neighbor_block to track if we are within a neighbor block.
        ring_neighbor_ip = None
    
        for i in range(group_start_idx + 1, group_end_idx):
            line = data.at[i, 'config'].strip()
            if line.startswith('cluster'):
                cluster = line.split()[1]  # Store the cluster IP
            if line.startswith('neighbor'):
                in_neighbor_block = True
                ring_neighbor_ip = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if find_value in description:  # Check if description does not contain "B40"
                    ring_neighbors[ring_neighbor_ip] = description
                in_neighbor_block = False
            elif line == 'exit':
                in_neighbor_block = False
    except IndexError:
        print("The target group 'RR-5-PEER' was not found in the file.")
    
    return ring_neighbors, cluster
 


def new_ring_bgp_group(new_group, new_description, ring_neighbors, cluster, start_key, old_import_policy, new_import_policy):
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
    if cluster is not None:
        print('                cluster {}'.format(cluster))
    print('                import "{}"'.format(new_import_policy))
    print('                export "{}"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
    print('                bfd-enable')
    print('                aigp')
    # Only print the cluster value if it exists (not None)
    if ring_neighbors:
    # Extract the first (and only) key and value
        ring_neighbor_ip = next(iter(ring_neighbors.keys()))
        description = ring_neighbors[ring_neighbor_ip]
        print ('                neighbor {}'.format(ring_neighbor_ip))
        print ('                    description "{}"'.format(ring_neighbors[ring_neighbor_ip]))
        print ('                    authentication-key "eNSEbgp"')
        print ('                exit')
    print('exit all')
    print('#--------------------------------------------------')


def rr_5_ensesr_csr_peer_west():
	start_key = 'group "RR-5-PEER"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-PEER'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_IRR"'
	new_description = 'Neighbor group for EVPN IRR' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_IRRW-IRR' 
    # Extract neighbors and cluster
	ring_neighbors, cluster = extract_ring_neighbors(my_file_pd, start_key, find_value)
	new_ring_bgp_group(new_group, new_description, ring_neighbors, cluster, start_key, old_import_policy, new_import_policy)

def rr_5_ensesr_csr_peer_east():
	start_key = 'group "RR-5-PEER"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-PEER'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_IRR"'
	new_description = 'Neighbor group for EVPN IRR' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_IRRE-IRR' 
    # Extract neighbors and cluster
	ring_neighbors, cluster = extract_ring_neighbors(my_file_pd, start_key, find_value)
	new_ring_bgp_group(new_group, new_description, ring_neighbors, cluster, start_key, old_import_policy, new_import_policy)



# In[13]:


#--- This is non B40 ring router
def extract_b40_neighbors(data, start_key, find_value):
    global b40_neighbors
    b40_neighbors = {}  # Ensure it is a dictionary
    try:
        # Find the start of the group "RR-5-ENSESR"
        group_start_idx = data[data['config'].str.contains(start_key)].index[0]
        group_end_idx_candidates = data[data['config'].str.contains(r'group ')].index.tolist()
        group_end_idx = next((idx for idx in group_end_idx_candidates if idx > group_start_idx), len(data))
        
        in_neighbor_block = False
        b40_neighbor_ip = None
    
        for i in range(group_start_idx + 1, len(data)):
            line = data.at[i, 'config'].strip()
            
            if line.startswith('neighbor'):
                in_neighbor_block = True
                b40_neighbor_ip = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if find_value in description:
                    b40_neighbors[b40_neighbor_ip] = description
                in_neighbor_block = False
            elif line == 'exit':
                in_neighbor_block = False
    except IndexError:
        print("The target group 'RR-5-PEER' was not found in the file.")
    
    return b40_neighbors 


def add_b40_neighbors(new_description, start_key, b40_neighbors, new_import_policy, new_group, old_import_policy):
    print('##---------------------------------------------------------')        
    print('######-----       Delete Old BGP Group      -------######')
    print('##---------------------------------------------------------')
    print('/configure router bgp')
    print('    {} shutdown'.format(start_key))
    print('    no {}'.format(start_key))
    print('        exit')
    print('/configure router policy-options')
    print('            begin')
    print('    no policy-statement "{}"'.format(old_import_policy))
    print('    no policy-statement "{}"'.format(old_import_policy.replace("IMPORT", "EXPORT")))
    print('        exit all')
    print('            commit')
    print('        exit')
    print('exit all')
    print('')
    print('##---------------------------------------------------------')        
    print('######-----        Add New BGP Group        -------######')
    print('##---------------------------------------------------------')
    print('/configure router bgp')
    print('    {}'.format(new_group))
    print('                description "{}"'.format(new_description))
    print('                family evpn label-ipv4')
    print('                type internal')
    print('                import "{}"'.format(new_import_policy))
    print('                export "{}"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
    print('                bfd-enable')
    print('                aigp')
    
    # Check if there are any neighbors in b40_neighbors
    if isinstance(b40_neighbors, dict) and b40_neighbors:
        # Extract the first (and only) key and value
        b40_neighbor_ip = next(iter(b40_neighbors.keys()))
        description = b40_neighbors[b40_neighbor_ip]
        print('                neighbor {}'.format(b40_neighbor_ip))
        print('                    description "{}"'.format(description))
        print('                    authentication-key "eNSEbgp"')
        print('                exit')
        print('exit all')
        print('#--------------------------------------------------')
    else:
        print("No B40 neighbors found.")



def rr_5_ensesr_ebh_west():
    start_key = 'group "RR-5-ENSESR-CLIENT"' #(Old group name)
    old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
    find_value = 'B40'
    new_group = 'group "RR-5-ENSESR_EBH"'
    new_description = 'Neighbor group for EVPN EBH Acess Leaf' 
    new_import_policy = 'IMPORT_RR-5-ENSESR_IRRW-EBH'
    b40_neighbors = extract_b40_neighbors(my_file_pd, start_key, find_value)
    add_b40_neighbors(new_description, start_key, b40_neighbors, new_import_policy, new_group, old_import_policy)

def rr_5_ensesr_ebh_east():
    start_key = 'group "RR-5-ENSESR-CLIENT"' #(Old group name)
    old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
    find_value = 'B40'
    new_group = 'group "RR-5-ENSESR_EBH"'
    new_description = 'Neighbor group for EVPN EBH Acess Leaf' 
    new_import_policy = 'IMPORT_RR-5-ENSESR_IRRE-EBH'
    b40_neighbors = extract_b40_neighbors(my_file_pd, start_key, find_value)
    add_b40_neighbors(new_description, start_key, b40_neighbors, new_import_policy, new_group, old_import_policy)


# In[14]:


def policy_bgp():
    print ('#--------------------------------------------------')
    print ('# New Policy Configuration')
    print ('#--------------------------------------------------')
    print('/configure router bgp')
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
    print ('        exit all')


def policy_remove():
    print ('#--------------------------------------------------')
    print ('# Remove Policy Configuration')
    print ('#--------------------------------------------------')
    print('/configure route policy-options')
    print ('            begin')
    print ('            {} no {}'.format(cmty_string[0],cmty_member ))
    print ('                no {}'.format(cmty_string[0] ))
    print ('            exit')
    print ('            commit')
    print ('        exit all')
    print('#--------------------------------------------------')
    print('## Cleaning LLD 1.2.1 policies ... ')
    print('#--------------------------------------------------')
    print('')
    print('/configure route policy-options')
    print('  begin')
    print('    no policy-statement "LABEL_LOOPBACK0"')
    print('    no policy-statement "EXPORT_RR-5-PEER"')
    print('    no policy-statement "IMPORT_RR-5-PEER"')
    print('    no policy-statement "EXPORT_RR-5-ENSESR"')
    print('    no policy-statement "IMPORT_RR-5-ENSESR"')
    print('    no policy-statement "EXPORT_RR-5-ENSESR-CLIENT"')
    print('    no policy-statement "IMPORT_RR-5-ENSESR-CLIENT"')
    print('  commit')
    print('exit all')
    print('')
    print('#--------------------------------------------------')
    print('## Cleaning LLD 1.2.1 prefix lists and communities ... ')
    print('#--------------------------------------------------')
    print('')
    print('/configure route policy-options')
    print('  begin')
    print('    no prefix-list "Default-Routes"')
    print('    no prefix-list "PRFX_LOCAL_SYSTEM_ADDRESS"')
    print('  commit')
    print('exit all')  
    print('#--------------------------------------------------')
    print('# Cleaning LLD 1.2.1 BGP groups ... ')
    print('#--------------------------------------------------')
    print('')
    print('/configure router bgp')
    print('    group "RR-5-ENSESR-CLIENT" shutdown')
    print('    no group "RR-5-ENSESR-CLIENT"')
    print('    group "RR-5-PEER" shutdown')
    print('    no group "RR-5-PEER"')
    print('    group "RR-5-ENSESR" shutdown')
    print('    no group "RR-5-ENSESR"')
    print('        exit all')


# In[15]:


# Create a function to print all the required bof routes to be added and deleted
def create_bof(old_statics):
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


# In[16]:


def policy_RR_5_ENSESR_IRRW_CSR():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRW-CSR"')
    print ('                description "EXPORT ROUTES TO RING CSRS"')
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
    print ('                    description "PROPAGATE EVPN"')
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
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRW-CSR"')
    print ('                description "IMPORT ROUTES FROM RING CSRS"')
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
#############################################################
def policy_RR_5_ENSESR_IRRW_EBH():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRW-EBH"')
    print ('                description "EXPORT ROUTES TO EBH AL"')
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
    print ('                    description "PROPAGATE EVPN"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRW-EBH"')
    print ('                description "IMPORT ROUTES FROM EBH AL"')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')
####################################################################
def policy_RR_5_ENSESR_IRRW_IRR():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRW-IRR"')
    print ('                description "EXPORT ROUTES TO PEER IRR"')
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
    print ('                    description "PROPAGATE EVPN"')
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
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRW-IRR"')
    print ('                description "IMPORT ROUTES FROM PEER IRR"')
    print ('                entry 10')
    print ('                    description "PREVENT LOOPBACK FROM REFLECTING BACK"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')

####################################################################
def policy_RR_5_ENSESR_IRRW_SPOKE():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRW-SPOKE"')
    print ('                description "EXPORT ROUTES TO SPOKE CSRS"')
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
    print ('                    description "PROPAGATE EVPN"')
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
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRW-SPOKE"')
    print ('                description "IMPORT ROUTES FROM SPOKE CSRS"')
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
####################################################################
#################### RING EAST      ###########################
####################################################################

def policy_RR_5_ENSESR_IRRE_CSR():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRE-CSR"')
    print ('                description "EXPORT ROUTES TO RING CSRS"')
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
    print ('                    description "PROPAGATE EVPN"')
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
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRE-CSR"')
    print ('                description "IMPORT ROUTES FROM RING CSRS"')
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


########################################################################
def policy_RR_5_ENSESR_IRRE_EBH():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRE-EBH"')
    print ('                description "EXPORT ROUTES TO EBH AL"')
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
    print ('                    description "PROPAGATE EVPN"')
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
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRE-EBH"')
    print ('                description "IMPORT ROUTES FROM EBH AL"')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')

##############################################################################
def policy_RR_5_ENSESR_IRRE_IRR():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRE-IRR"')
    print ('                description "EXPORT ROUTES TO PEER IRR"')
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
    print ('                    description "PROPAGATE EVPN"')
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
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRE-IRR"')
    print ('                description "IMPORT ROUTES FROM PEER IRR"')
    print ('                entry 10')
    print ('                    description "PREVENT LOOPBACK FROM REFLECTING BACK"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')

#########################################################################
def policy_RR_5_ENSESR_IRRE_SPOKE():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRE-SPOKE"')
    print ('                description "EXPORT ROUTES TO SPOKE CSRS"')
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
    print ('                    description "PROPAGATE EVPN"')
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
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRE-SPOKE"')
    print ('                description "IMPORT ROUTES FROM SPOKE CSRS"')
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


######################################################################################
#################################### RING NODE      ##################################
######################################################################################
def policy_RR_5_ENSESR_IRR():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_CSR-IRR"')
    print ('                description "EXPORT ROUTES TO IRRS"')
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
    print ('            policy-statement "IMPORT_RR-5-ENSESR_CSR-IRR"')
    print ('                description "IMPORT ROUTES FROM IRRS"')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')

###########################################################################################

def policy_RR_5_ENSESR_CSR_SPOKE():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_CSR-SPOKE"')
    print ('                description "EXPORT ROUTES TO SPOKE CSRS"')
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
    print ('                description "IMPORT ROUTES FROM SPOKE CSRS"')
    print ('                entry 5')
    print ('                    description "DROP DEFAULT ROUTE"')
    print ('                    from')
    print ('                        prefix-list "PRFX_DEFAULT"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
    print ('                entry 10')
    print ('                    description "IMPORT LEARNED BGP LABELS"')
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
    print ('                    description "IMPORT LEARNED EVPN ROUTES"')
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

###########################################################################################
def policy_RR_5_ENSESR_SPOKE_CSR():
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
    print ('            policy-statement "IMPORT_RR-5-ENSESR_SPOKE-CSR"')
    print ('                description "IMPORT ROUTES FROM A CSR"')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')
    print ('            commit')

###########################################################################################
def policy_RR_5_ENSESR_CSR_IRR():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_CSR-IRR"')
    print ('                description "EXPORT ROUTES TO IRRS"')
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
    print ('            policy-statement "IMPORT_RR-5-ENSESR_CSR-IRR"')
    print ('                description "IMPORT ROUTES FROM IRRS"')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')


# In[17]:


def site_int():
    # B40 01 and 02 file for isis metric and bgp neighbor to a new group and delete neighbor from existing group.
    #print(b40facinginterface)
    print('########### Following info is Just to verify the interface and  system info ############')
    print('# System Name: {}", "system ip: {}",  '.format(name, system_ip))
    print('########################################################################################')
    print('')
    print('#### PLEASE LOGIN TO THE ROUTER USING point to point ip address, so as not to loose the connectivity when BGP is down. #####')
    print('/show system rollback')
    print('/admin rollback save comment "Pre-update Checkpoint"')
    print('')
    if ecmp_value[1] != '2':
        print('#--------------------------------------------------')
        print("# This router has ecmp value of 2, please change it to ecmp 1")
        print('#--------------------------------------------------')
        print('/configure router ecmp 1')
    print('#--------------------------------------------------')
    print('# New Interface Configuration')
    print('#--------------------------------------------------')
    print('')
    for interface_desc, description in metric_interface.items():
        print('/configure router isis 5 {} level 1 metric 1000000'.format(interface_desc))
    print('')
    print('/configure router interface "system" bfd 100 receive 100 multiplier 3')
    print('')
    print('#--------------------------------------------------')
    print('# Update ISIS 5 overload timout')
    print('#--------------------------------------------------')
    print('')    
    print('/configure router isis 5 overload-on-boot timeout 180')
    print('/configure port 1/1/24 ethernet speed 1000')
    print('')
    #print('/configure router bgp shutdown')
    #print('/configure router no bgp')
    #print(b40_name
    


# In[18]:


def new_qos():
    print('#--------------------------------------------------')
    print('# New QOS Configuration')
    print('#--------------------------------------------------')
    print('/configure qos')
    print('        port-qos-policy "40012" create')
    print('            description "eNSE SR Network Port QOS Policy"')
    print('            queue "1" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 24.00')
    print('                exit')
    print('            exit')
    print('            queue "2" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 3.00')
    print('                exit')
    print('            exit')
    print('            queue "3" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 1.00')
    print('                exit')
    print('            exit')
    print('            queue "4" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 3.00')
    print('                exit')
    print('            exit')
    print('            queue "5" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 8.00')
    print('                exit')
    print('            exit')
    print('            queue "6" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 55.00')
    print('                exit')
    print('            exit')
    print('            queue "7" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 5.00')
    print('                exit')
    print('            exit')
    print('            queue "8" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 1.00')
    print('                exit')
    print('            exit')
    print('        exit all')


# In[19]:


# B40 group change and check interface to 1000000

def b40_01_changes_ixre(system_ip, name):
    print ('###Remove neighbor from 121 bgp group ONLY after adding the bgp on B40-01 and 02')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------')
    print ('# Check for the routers interface metric under ISIS 5"')
    print ('#--------------------------------------------------')
    print ('admin display-config | match "{}" context all'.format(name))
    print ('/show router isis 5 interface | match "site interface"')
    #print ('/configure router isis 5 interface " level 1 metric 1000000
    print ('If the above interface level 1 metric is not 1000000 then change it to 1000000')


def b40_02_changes_ixre(system_ip, name):
    print ('###Remove neighbor from 121 bgp group after you have brought up 135 BGP neigh on B40-01 and 02')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------')
    print ('# Check for the routers interface metric under ISIS 5"')
    print ('#--------------------------------------------------')
    print ('admin display-config | match "{}" context all'.format(name))
    print ('/show router isis 5 interface | match "site interface"')
    print ('If the interface level 1 metric is not 1000000 then change it to 1000000')


# B40 group change and check interface to 1000000

def b40_01_rollback_ixre(system_ip, name):
    print ('')
    print ('')
    print ('')
    print ('###################################################')
    print ('#     ROLLBACK FOR B40-01     "')
    print ('#--------------------------------------------------')
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_IRR" no neighbor {}'.format(system_ip))
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
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_IRR" no neighbor {}'.format(system_ip))
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
    print ('/show router isis 5 interface | match "site interface"')
    print ('If the interface level 1 metric is not 1000000 then change it to 1000000')


# In[20]:


# Post check ping check script / 
def pre_post_b40():
    print ('')
    print ('#--------------------------------------------------')
    print ('# Local IXRE post checks "')
    print ('#--------------------------------------------------')
    print ('show service sap-using')
    print ('show port A/gnss')
    print ('show system ptp port')
    print ('show router 1 interface')
    print ('show router 4 interface')
    print ('show router policy')
    print ('show router bgp summary')
    print ('')
    print ('#--------------------------------------------------')
    print ('# B40 post checks for pinging CSR interfaces from B40-01 and 02"')
    print ('#--------------------------------------------------')
    print('\show router bgp summary')
    for ran in vprn1_ip:
        print('ping router-instance "RAN" {}'.format(ran.split('/', 1)[0][8:]))
    for mgm in vprn4_ip:
        print('ping router-instance "CELL_MGMT" {}'.format(mgm.split('/', 1)[0][8:]))


# In[21]:


def find_unnumbered_int(data):
    global found_interface
    group_start_idx = data[data['config'].str.contains('echo "Router')].index[0]
    group_end_idx = data[data['config'].str.contains('echo "MPLS Label')].index[0]

    found_interface = []
    found_unnumbered = False 

    # Loop through the DataFrame between start and end indices, from end to start
    for i in range(group_end_idx - 1, group_start_idx - 1, -1):
        line = data.at[i, 'config'].strip()
        if line.startswith('unnumbered'):
            found_unnumbered = True 
        elif found_unnumbered and line.startswith('interface'):
            found_port = line.split()[1]  # get the port
            found_interface.append(found_port)
            found_unnumbered = False  # reset flag

    if found_interface:
        print(f"Ports with unnumbered: {found_interface}")
    else:
        print("No unnumbered port found")

    return found_interface

# Call the function on your DataFrame
#scan_file()
#all_files()
#for items in path:
#    create_pd()
#    unnumbered_ports = find_unnumbered_int(my_file_pd)
#    print(f"Ports with unnumbered: {unnumbered_ports}")


# In[22]:


def main():
    global items, folder 
    all_files()
    cwd = os.getcwd()  # Save the current directory to return back after each iteration
    print(cwd)
    for items in path:
        os.chdir(cwd)
        #print(items)
        try:
            create_pd()
            print(name)

            # Find what kind of a node is it B40, Ring, Spoke
            grp_peer = my_file_pd.index[my_file_pd['config'].str.contains('group "RR-5-PEER"')].tolist()
            grp_r5_enesr_client = my_file_pd.index[my_file_pd['config'].str.contains('group "RR-5-ENSESR-CLIENT"')].tolist()  # to B40 or AL or HUB
            grp_peer_e = my_file_pd.index[(my_file_pd['config'].str.contains('group "RR-5-PEER"')) & (my_file_pd['config'].shift(-1).str.contains('IRR-W to IRR-E'))].tolist()
            grp_peer_w = my_file_pd.index[(my_file_pd['config'].str.contains('group "RR-5-PEER"')) & (my_file_pd['config'].shift(-1).str.contains('IRR-E to IRR-W'))].tolist()
            grp_rr_5_ENSESR = my_file_pd.index[my_file_pd['config'].str.contains ('group "RR-5-ENSESR"')].tolist() #--- These are spokes and CSR 

            has_B40 = my_file_pd.index[(my_file_pd['config'].str.contains('import "IMPORT_RR-5-ENSESR-CLIENT') & my_file_pd['config'].shift(-6).str.contains('description.*B40'))].tolist()
            # This following is to use invert operator to ensure there is no b40 in description.
            has_no_B40_but_spoke = my_file_pd.index[(my_file_pd['config'].str.fullmatch('import "IMPORT_RR-5-ENSESR-CLIENT"') & ~ my_file_pd['config'].shift(-6).str.contains('description.*B40', na=False))].tolist() 
            
    
            if not os.path.isdir(name):
                os.mkdir(name)
            os.chdir(name)
            folder = os.getcwd()

            # IXRE config changes based on policies
            sys.stdout = open(folder + '/' + name + '_LLD135.cfg', 'w')
            metric_int(my_file_pd)
            site_int()              
            policy_bgp()

    #----------------------------------------------------------------------
            if bool(has_B40):        #and len(is_B40)>=1
                b40_name_get()
                if '01' in b40_name:
                    print("# This is a West Node")
                    policy_RR_5_ENSESR_IRRW_EBH() # for ring b40 node (tested)
                    rr_5_ensesr_ebh_west() # (tested)
                    if bool(grp_rr_5_ENSESR):
                        spoke_bgp_neighbors, csr_bgp_neighbors, cluster = extract_neighbors(my_file_pd,'group "RR-5-ENSESR"')
                        #print(spoke_bgp_neighbors, csr_bgp_neighbors)
                        if len(spoke_bgp_neighbors)>=1:
                            policy_RR_5_ENSESR_IRRW_SPOKE() # for west spokes
                            RR_5_ENSESR_IRRW_SPOKE() #group "RR-5-ENSESR_SPOKE" for spoke west neighbors
                        if len(csr_bgp_neighbors)>=1:
                            policy_RR_5_ENSESR_IRRW_CSR() # policy for the CSR non spoke ixre
                            RR_5_ENSESR_IRRW_CSR() # group "RR-5-ENSESR_CSR" for non spoke csr neighbors
                if '02' in b40_name:
                    print("# This is a East Node")
                    policy_RR_5_ENSESR_IRRE_EBH() # for ring b40 node (tested)
                    rr_5_ensesr_ebh_east() # (tested)
                    if bool(grp_rr_5_ENSESR):
                        spoke_bgp_neighbors, csr_bgp_neighbors, cluster = extract_neighbors(my_file_pd,'group "RR-5-ENSESR"')
                        #print(spoke_bgp_neighbors, csr_bgp_neighbors)
                        if len(spoke_bgp_neighbors)>=1:
                            policy_RR_5_ENSESR_IRRE_SPOKE() # for east spokes
                            RR_5_ENSESR_IRRE_SPOKE() #group "RR-5-ENSESR_SPOKE" for spoke east neighbors
                        if len(csr_bgp_neighbors)>=1:
                            policy_RR_5_ENSESR_IRRE_CSR() # policy for the CSR non spoke ixre
                            RR_5_ENSESR_IRRE_CSR() # group "RR-5-ENSESR_CSR" for non spoke csr neighbors
        #----------------------------------------------------------------------------------------------------------------#
            if bool(grp_peer_e) and '02' in b40_name:
            #    print(grp_peer_e)
                policy_RR_5_ENSESR_IRRE_IRR()
                rr_5_ensesr_csr_peer_east()
            if bool(grp_peer_w) and '01' in b40_name:
                policy_RR_5_ENSESR_IRRW_IRR()
                rr_5_ensesr_csr_peer_west()                
 #-----------------------------------    Ring Node    ------------------------------------------------#               
            if bool(grp_rr_5_ENSESR) and not bool(has_B40)and not bool(grp_peer): # If it has no B40 and is a Ring node
                policy_RR_5_ENSESR_CSR_IRR() # for CSR that is not a spoke
                rr_5_ensesr_IRR() #group "RR-5-ENSESR-CLIENT" to east or west ring node NOT B40
            if bool(grp_r5_enesr_client) and not bool(has_B40) and not bool(grp_peer) and bool(grp_rr_5_ENSESR):
                policy_RR_5_ENSESR_CSR_SPOKE() # for ring spokes
                rr_5_csr_ring_spoke() #group "RR-5-ENSESR_SPOKE" for spoke on ring nodes (policy "IMPORT_RR-5-ENSESR_CSR-SPOKE")

#-----------------------------------    Spoke    ------------------------------------------------#
            if bool(grp_r5_enesr_client) and not bool(grp_rr_5_ENSESR) and not bool(grp_rr_5_ENSESR):
                policy_RR_5_ENSESR_SPOKE_CSR() # for CSR that is not a spoke
                rr_5_ensesr_spoke() #group "RR-5-ENSESR-CLIENT" for east or west ring node NOT B40
            
#-----------------------------------    BOF and post checks     ----------------------------------------------------------#
            sys.stdout = open(folder + '/' + name + '_bof.cfg', 'w')
            bof_data()
            create_bof(old_statics)

            sys.stdout = open(folder + '/' + name + '_Post_Checks.txt', 'w')
            post_checks()
            extract_vprn_info(my_file_pd)

            os.chdir(cwd)  # up directory

        except Exception as e:
            # Log the error
            #logging.error(f"Error processing file {items}: {e}")
            continue  # skip to  next item in the for loop


# In[23]:


if __name__ == "__main__":
    if check_for_update():
        restart_script()
    else:
        main()


# In[ ]:





# In[ ]:




