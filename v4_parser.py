import pandas as pd
import json

class V4Parser():
    def __init__(self, v4data_fpath):

        self.headers = {'COMHD': 'Company Header', 
                        'RTEHD': 'Route Header', 
                        'PRMDT': 'Premises Detail', 
                        'PRMD2': 'Premise Detail Alternate', 
                        'MTRDT': 'Meter Detail', 
                        'RDGDT': 'Read Detail', 
                        'RTETR': 'Route Trailer', 
                        'COMTR': 'Company Trailer', 
                        'PRMNT': 'Premises Notes', 
                        'ORDST': 'Order Status'}

        self.v4_fpath = v4data_fpath
        self.v4 = self.read_v4_file()
        self.schema_fpath = "./resources/schema_information.xlsx"
        self.schema = self.read_schema()
        # Sets route number and file type (import / export)/
        self.get_set_file_meta_data()
        self.parse_template = self.create_parse_template()
        self.data = self.parse_v4_to_json()


    def __repr__(self):
        return (f"V4 Parser Info: File [{self.v4_fpath}] is a ({self.v4_type}) File Containing: {len(self.v4)} lines. "
                f"There are {self.num_routes} routes in this file.")


    def read_v4_file(self):

        with open(self.v4_fpath, "r") as inf:
            return inf.readlines()
        

    def read_schema(self):
        
        if self.schema_fpath.endswith(".csv"):
            return pd.read_csv(self.schema_fpath)
        else:
            return pd.read_excel(self.schema_fpath, "Field Map")
        

    def get_set_file_meta_data(self):

        counts = {}
        for i, line in enumerate(self.v4):
            line_type = self.headers[line[:5]]
            if line_type not in counts.keys():
                counts[line_type] = 1
            else:
                counts[line_type] = counts[line_type] + 1

        if "Order Status" in counts.keys():
            self.v4_type = "export"
        else:
            self.v4_type = "import"

        assert counts["Route Header"] == counts["Route Trailer"]
        self.num_routes = counts["Route Header"]

        print(counts)


    def create_parse_template(self):

        parse_template = {}
        for g in self.schema.groupby("Layout Type"):    
            parse_template[g[0]] = {row[1]["Column"]: {"Start": int(row[1]["Offset"].split("-")[0]) - 1, 
                                                       "Size": row[1]["Length"]} for row in g[1].iterrows()}

        return parse_template
    

    def parse_line(self, line, parser):

        # Checks that the data is consistent with the spec. Lines should add up to the buffer
        # size for each line. This ensures that this can be p[arsed propery.
        assert len(line) == sum([val["Size"] for val in parser.values()])

        unpacked_data = {}
        for col_name in parser.keys():
            st = parser[col_name]["Start"]
            end = parser[col_name]["Start"] + parser[col_name]["Size"]
            unpacked_data[col_name] = line[st:end].strip()

        
        return unpacked_data


    def parse_v4_to_json(self):

        all_data = {}
        current_route = ""
        current_prem = ""
        for line in self.v4:
            line_type = self.headers[line[:5]]
            parser = self.parse_template[line_type]
            data = self.parse_line(line, parser)
            
            if line_type == "Route Header":
                current_route = data["Route"]
                all_data[current_route] = data
                all_data[current_route]["Data"] = {}
            elif line_type == "Route Trailer":
                all_data[current_route]["# Premises"] = data["# Premises"]
                all_data[current_route]["# Meters"] = data["# Meters"]
            elif current_route == "":
                continue
            else:
                all_data[current_route]["Data"][line_type] = data

        
        with open("out.json", "w") as outf:
            json.dump(all_data, outf, indent=4)


        




if __name__ == "__main__":
    parser = V4Parser("./sample_data/aug_9_v4_2.exp")
    print(parser)