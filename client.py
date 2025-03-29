import sys
import os
import threading
import random
import glob
from collections import deque
import numpy as np
import time


sys.path.append('gen-py')
sys.path.insert(0, glob.glob('../thrift-0.19.0/lib/py/build/lib*')[0])
from thrift import Thrift
from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol
from thrift.server import TServer

from supernode import super
from supernode.ttypes import Node
from compute import compute

from ML import *

class ClientHandler: 
    def __init__(self, supernode_host= '0.0.0.0', supernode_port=9091):
        self.supernode_host = supernode_host
        self.supernode_port = supernode_port
        self.connection_point = None
        
    '''
    Connect to another node in the network
    '''
    def connect_to_supernode(self):
        try:
            transport = TSocket.TSocket(self.supernode_host, self.supernode_port)
            transport = TTransport.TBufferedTransport(transport)
            protocol = TBinaryProtocol.TBinaryProtocol(transport)
            client = super.Client(protocol)
            transport.open()
            return client, transport  
        except Exception as e:
            print(f"Failed to connect to node {self.supernode_host}:{self.supernode_port} - {e}")
            return None, None  
    
    '''
    Connect to another node in the network
    '''
    def connect_to_node(self, host, port):
        try:
            transport = TSocket.TSocket(host, port)
            transport = TTransport.TBufferedTransport(transport)
            protocol = TBinaryProtocol.TBinaryProtocol(transport)
            client = compute.Client(protocol)
            transport.open()
            return client, transport  
        except Exception as e:
            print(f"Failed to connect to node {host}:{port} - {e}")
            return None, None  

    '''
    Receive a connection point from supernode to join the network
    Returns 0 on success; otherwise -1
    '''
    def join_network(self):
        # connection_point = super.get_node() # Node(ip, port)
        # conn_ip, conn_port = connection_point.ip, connection_point.port 
        client, transport = self.connect_to_supernode()

        if client and transport:
            try:
                # Get connection point
                connection_point = client.get_node() # Node(ip, port)
                conn_ip, conn_port = connection_point.ip, connection_point.port 

                if conn_ip is not None and conn_port is not None:
                    self.connection_point = connection_point
                    print(f"Connected to network via node at ip - {conn_ip} and port - {conn_port}")
                    return 0
                else:
                    print(f"Fail to connect to network via node at ip - {conn_ip} and port - {conn_port}")
                    return -1

            # Ensures that connection would be closed
            finally: 
                transport.close() 
        else:
            print(f"Fail to connect to supernode")
            return -1
    
    '''
    Get files in a directory and store in list 
    '''
    def get_files(self, dir):
        files = []
        for f in os.listdir(dir):
            if os.path.isfile(os.path.join(dir, f)):
                fname = os.path.join(dir, f)
                files.append(fname)

        return files

    '''
    Distributes training files into the network of nodes 
    Returns 0 on success; otherwise -1
    '''
    def distribute_data(self, dir):
        # Sanitize
        if not dir or not os.path.exists(dir) or not os.path.isdir(dir):
            print(f"Error: Invalid directory '{dir}'")
            return -1
        
        if not self.connection_point:
            print("Error: Not connected to network")
            return -1
        
        files = self.get_files(dir=dir)

        print(f"Distributing {len(files)} files across the network...")

        # Connect to connection point
        conn_ip, conn_port = self.connection_point.ip, self.connection_point.port 
        client, transport = self.connect_to_node(conn_ip, conn_port)

        if client and transport:
            try:
                for f in files:
                    print(f"Putting file {f} into network...")
                    client.put_data(f)
                print("Data distribution complete!")
                return 0
            # Ensures that connection would be closed
            finally: 
                transport.close() 
    
    '''
    Get combined trained models from the network of compute nodes to be validated 
    Returns 0 on success; otherwise -1
    '''
    def aggregrate_models(self, dir):
        # Sanitize
        if not dir or not os.path.exists(dir) or not os.path.isdir(dir):
            print(f"Error: Invalid directory '{dir}'")
            return -1

        
        if not self.connection_point:
            print("Error: Not connected to network")
            return -1
        
        files = self.get_files()
        
        print(f"Collecting models for {len(files)} files from the network...")

        # Connect to connection point 
        conn_ip, conn_port = self.connection_point.ip, self.connection_point.port 
        client, transport = self.connect_to_node(conn_ip, conn_port)

        if client and transport:
            try:
                shared_gradient_V = None
                shared_gradient_W = None
                models_collected = 0

                for f in files:
                    # Tries to get model again if was not ready
                    tries = 2

                    for t in range(tries):
                        print(f"Getting model for {f} (attempt {t+1})...")
                        model = client.get_model(f)
 
                    if model.status == "ready":
                        print(f"Model for {f} has been aggregrated!")
                        # Convert lists back to numpy arrays
                        V = np.array(model.V)
                        W = np.array(model.W)
                        
                        # Add to sums
                        if shared_gradient_V is None:
                            shared_gradient_V = V
                            shared_gradient_W = W
                        else:
                            shared_gradient_V += V
                            shared_gradient_W += W
                        
                        models_collected+= 1
                        break
                    elif model.status == "wait":
                        print(f"Model for {f} is not ready, wait....")
                        time.sleep(2)  # Wait for 2s before trying again
                    else:  
                        print(f"Model for {f} not found!")
                        break

                print(f"Aggregated {models_collected} models")

                if models_collected == 0:
                    print("No models collected")
                    return -1
                
                # Average the models
                shared_gradient_V = scale_matricies(shared_gradient_V, 1.0/models_collected)
                shared_gradient_W = scale_matricies(shared_gradient_W, 1.0/models_collected)

                # Validate aggregated model
                model = mlp()
                
                validate_file = os.path.join(dir, "validate_letters.txt")
                # Initialize model before training
                initialized_model = model.init_training_model(validate_file, shared_gradient_V, shared_gradient_W)
                if (initialized_model == False):
                    raise Exception(f"Model initialization failed with file {f}")
                validation_error = model.validate(validate_file)
                print(f"Validation error: {validation_error}")

                return 0
        
            # Ensures that connection would be closed
            finally: 
                transport.close() 
    

# Main client program
if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python client.py <training_dir> <supernode_port>")
        sys.exit(1)
    
    training_dir = sys.argv[1]
    supernode_port = sys.argv[2]

    # Create client
    client = ClientHandler(supernode_port=supernode_port)
    
    # Connect to network
    if client.join_network() == -1:
        print("Failed to connect to network")
        sys.exit(1)
    
    # Distribute data
    if client.distribute_data(training_dir) == -1:
        print("Failed to distribute data")
        sys.exit(1)
    
    # Wait a bit for training to progress
    print("Waiting for training to complete...")
    time.sleep(10)
    
    # Aggregate models and validate
    if client.aggregrate_models(training_dir) == -1:
        print("Failed to aggregate models")
        sys.exit(1)