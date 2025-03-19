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


class SuperHandler:
    def __init__(self, max_nodes=10):
        # Maximum nodes in the network
        self.max_nodes = max_nodes

        # Dict storing active nodes in the network
        self.active_nodes = {}

        # Dict storing nodes from compute_nodes.txt
        self.compute_nodes = {}

        # Set to keep track of node IDs (ensures uniqueness)
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
                    self.compute_nodes[int(port)] = host
        except Exception as e:
            print(f"Error parsing compute nodes: {e}")
            sys.exit(1)

    def generate_id(self, active_nodes,max_nodes) :
        # ID be between 0 and max num of nodes  - 1
        node_id = active_nodes % max_nodes

        if node_id not in self.node_ids:
            return node_id
        else:
            print("Node id already present in the network")

        


    def request_join(self, port):
        # Populate the active node dict 
        self.generate_id()

        # Cross reference port num with config file


        # Store in active node dict


        # One node join at the same time 


        # Send NACK if 


        pass

    def confirm_join(self, node_id):
        pass

    def get_node(self):
        pass

    def print_info(self):
        pass