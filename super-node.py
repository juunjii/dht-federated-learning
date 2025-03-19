import sys
import os
import threading
import random
import glob
from collections import deque
import numpy as np


sys.path.append('gen-py')
sys.path.insert(0, glob.glob('../thrift-0.19.0/lib/py/build/lib*')[0])
from thrift import Thrift
from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol
from thrift.server import TServer



# from coordinator import coordinator
from super import super
from ML import *


# Macro for max nodes possbile in network
MAX_NODES = 10


class SuperHandler:
    def __init__(self, max_nodes=10):
        # Maximum nodes in the network
        self.max_nodes = max_nodes

        # Dict storing active nodes in the network
        # {node_id: (ip: port}
        self.active_nodes = {}

        # Dict storing nodes from compute_nodes.txt
        # {ip : port}
        self.compute_nodes = {}

        # Set to keep track of node IDs of active nodes 
        self.node_ids = set()

        # To enforce one node joining network per time
        self.node_joining = None

        self.parse_compute_nodes()


    '''
    Parse list of compute nodes from text file; 
    Gets compute nodes' respective ip and port
    '''
    def parse_compute_nodes(self):
        try:
            with open('compute_nodes.txt', 'r') as file:
                for line in file:
                    host, port = line.strip().split(',')
                    self.compute_nodes[host] = int(port)
        except Exception as e:
            print(f"Error parsing compute nodes: {e}")
            sys.exit(1)

    '''
    Generate unique id for nodes
    '''
    def generate_id(self, max_nodes) :
        if max_nodes > 10:
            return -1

        # Ensures ID between 0 and max num of nodes - 1
        for node_id in range(max_nodes):
            if node_id not in self.node_ids:
                self.node_ids.add(node_id)
                return node_id
        

    ''' 
    Returns a unique ID to use when joining the network 
    '''
    def request_join(self, port):
        # Sanitize input
        if port not in self.compute_nodes:
            print(f"Error: Port {port} is not in config file.")
            return -1

        # Ensure singular node joins network at a time
        if self.node_joining is not None:
            print(f"NACK: Node {self.node_joining} is joining the network...Try again later...")
            return -1
        
        # Return unique node id
        node_id = self.generate_id(self.max_nodes)
        if node_id == -1:
            print(f"Error: {self.max_nodes} exceeds the maximum number of possible nodes in the network - {MAX_NODES}")

        # Tracks current node joining network
        self.node_joining = node_id

        print(f"Node joining with port {port} assigned ID: {node_id}")

        return node_id
       

    '''
    Confirm a new node's join status in the network 
    '''
    def confirm_join(self, node_id):

        # Check node join status
        if node_id != self.node_joining:
            print(f"Node {node_id} did not join the network")
            return
        
        # Node succesfully joined!

        for 

        # Update active node dict
        self.active_nodes[node_id] = port

        

    def get_node(self):
        pass

    def print_info(self):
        pass