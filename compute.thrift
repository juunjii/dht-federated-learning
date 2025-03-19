// Struct to hold weight matrices
struct WeightMatrices {
    1: list<list<double>> V,
    2: list<list<double>> W
}

service compute {
    # Place input ML data (filename) into the network 
    oneway void put_data(1: string filename)
    
    # Returns a model from a node from an input dataset (filename)
    WeightMatrices get_model(1: string filename) 
    
    # Node fixes finger table after a new node joins
    void fix_fingers() 
    
    # Print node information for debugging
    string print_info()
    
    # Node-specific Chord operations
    i32 get_id()
    string get_successor()
    string get_predecessor()
    void set_predecessor(1: string pred_addr, 2: i32 pred_id)
    list<string> get_finger_table()
    i32 find_successor(1: i32 id)
    void notify(1: i32 node_id, 2: string node_addr)
}