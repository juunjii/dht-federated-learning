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

from super import super


def main():
    
    # Make socket
    transport = TSocket.TSocket('127.0.0.1', 9091)
    transport = TTransport.TBufferedTransport(transport)
    protocol = TBinaryProtocol.TBinaryProtocol(transport)

    client = super.Client(protocol)

    try:
        # Connect to super node 
        transport.open()

        # Test the supernode functionality
        print("Testing supernode functionality:\n")
        
        # Print initial info
        print("~~~~~~~~~~~~~~~~~~~~~~~~~")
        print("Initial supernode info:")
        print("~~~~~~~~~~~~~~~~~~~~~~~~~")

        print(client.print_info())

        node_id = client.request_join(8000)
        print(f"Requested join with port 8000, got node ID: {node_id}")
        
        # Confirm join
        client.confirm_join(node_id)
        print(f"Confirmed join for node ID: {node_id}")
        
        # Try to get a node
        node_address = client.get_node()
        print(f"Got node address: {node_address}\n")
        
        # Print updated info
        print("~~~~~~~~~~~~~~~~~~~~~~~~~")
        print("Updated supernode info:")
        print("~~~~~~~~~~~~~~~~~~~~~~~~~")
        print(client.print_info())

        # Close!
        transport.close()

    except Thrift.TException as tx:
        print(f"Thrift Exception: {tx.message}")


if __name__ == '__main__':
    try:
        main()
    except Thrift.TException as tx:
        print('%s' % tx.message)