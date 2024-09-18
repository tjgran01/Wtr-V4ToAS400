import pandas as pd
import json


class MalformedReadError(Exception):
    def __init__(self, message, counts):

        formatted = []
        for key, v in counts.items():
            formatted.append(f"{key}: \t {v} \n")

        message = f"{message}\n\n{"".join(formatted)}"
        super().__init__(message)
        self.message = message


class UnclosedRouteError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class InvalidBufferSizeError(Exception):
    def __init__(self, line_type, line_len, schema_len):
        self,message = f"Mismatch between schema line len ({schema_len}) and actual line lenth in datafile ({line_len}) for line type: {line_type}."
        super().__init__(self.message)



class V4Parser():
    def __init__(self, v4data_fpath):

        self.headers = {'COMHD': 'Company Header', 
                        'RTEHD': 'Route Header', 
                        'PRMDT': 'Premise Detail', 
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
        # Sets route number and file type (import / export)
        self.get_set_file_meta_data()
        self.parse_template = self.create_parse_template()
        self.json = self.parse_v4_to_json()


    def __repr__(self):

        read_line = f"There are {self.num_reads} reads in this file."

        if self.num_routes == 1:
            return (f"V4 Parser Info: File [{self.v4_fpath}] is a ({self.v4_type}) File Containing: {len(self.v4)} lines. "
                    f"There is {self.num_routes} route in this file. {read_line}")
        else:
            return (f"V4 Parser Info: File [{self.v4_fpath}] is a ({self.v4_type}) File Containing: {len(self.v4)} lines. "
                    f"There are {self.num_routes} routes in this file. {read_line}")



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

        validation_set_list = [counts['Meter Detail'], counts['Read Detail'], counts['Premise Detail'], counts['Premises Notes']]

        if "Order Status" in counts.keys():
            self.v4_type = "export"
            validation_set_list.append(counts["Order Status"])
        else:
            self.v4_type = "import"

        validation_set = set(validation_set_list)

        try:
            assert len(validation_set) == 1
            self.num_reads = counts['Meter Detail']
        except AssertionError:
            raise MalformedReadError(f"The number of read fields are not consistent. Some information is missing from this v4 file...", counts)
        
        try:
            assert counts["Route Header"] == counts["Route Trailer"]
            self.num_routes = counts["Route Header"]
        except AssertionError:
            raise UnclosedRouteError((f"Number of route trailers ({counts['Route Trailer']}) does not match number of route headers ({counts['Route Trailer']})",
                                     "File is maleformed and cannot be parsed!"))


    def create_parse_template(self):

        parse_template = {}
        for g in self.schema.groupby("Layout Type"):    
            parse_template[g[0]] = {row[1]["Column"]: {"Start": int(row[1]["Offset"].split("-")[0]) - 1, 
                                                       "Size": row[1]["Length"]} for row in g[1].iterrows()}

        return parse_template
    

    def parse_line(self, line, parser):

        # Checks that the data is consistent with the spec. Lines should add up to the buffer
        # size for each line. This ensures that this can be parsed propery.

        try:
            assert len(line) == sum([val["Size"] for val in parser.values()])
        except AssertionError:
            raise InvalidBufferSizeError(line[:5], len(line), sum([val["Size"] for val in parser.values()]))

        unpacked_data = {}
        for col_name in parser.keys():
            st = parser[col_name]["Start"]
            end = parser[col_name]["Start"] + parser[col_name]["Size"]
            if col_name != "CRLF":
                unpacked_data[col_name] = line[st:end].strip()

        return unpacked_data


    def parse_v4_to_json(self):

        self.json = {}
        current_route = ""

        ltypes = ["Premise Detail", "Premises Notes", "Meter Detail", "Read Detail"]
        if self.v4_type == "export":
            ltypes.append("Order Status")

        data_buffer = {}
        read_information_index = 0
        for line in self.v4:

            line_type = self.headers[line[:5]]
            parser = self.parse_template[line_type]
            data = self.parse_line(line, parser)

            if line_type == "Route Header":
                current_route = data["Route"]
                self.json[current_route] = data
                self.json[current_route]["Data"] = {}
            elif line_type == "Route Trailer":
                self.json[current_route]["# Premises"] = data["# Premises"]
                self.json[current_route]["# Meters"] = data["# Meters"]
            elif current_route == "":
                continue
            else:
                data_buffer[line_type] = data
                # If I have a value for every single header that I need, then I can push the data. Otherwise,
                # keep putting the data in the buffer.
                if set(list(data_buffer.keys())) == set(ltypes):
                    self.json[current_route]["Data"][data_buffer["Premise Detail"]["Account Number"]] = data_buffer
                    data_buffer = {}
        
        with open("./cache/out.json", "w") as outf:
            json.dump(self.json, outf, indent=4)

        return self.json
    

    def parse_json_to_radio(self):

        _lines = []
        for route, route_data in self.json.items():
            for account_number, read_data in route_data["Data"].items():
                if "Order Status" in read_data.keys():
                    ts = read_data["Order Status"]["Time Stamp"]
                else:
                    ts = ""
                row = {"ROUTE": route,
                       "WALK": "",
                       "PAGN": read_data["Meter Detail"]["Read Sequence"],
                       "RESQ": "",
                       "HHELD": "N360",
                       "RDIR": "",
                       "NDIAL": read_data["Read Detail"]["Dials"],
                       "IDEXP": read_data["Read Detail"]["Collection ID"],
                       "IDCAP": read_data["Read Detail"]["Collection ID"],
                       "IDOVR": "",
                       "DECI": read_data["Read Detail"]["Decimals"],
                       "MREAD": read_data["Read Detail"]["Reading"],
                       "READO": read_data["Read Detail"]["Reading"],
                       "HIGHR": "",
                       "LOWR": "",
                       "DTER": "",
                       "DTEE": "",
                       "NOTES": "",
                       "LOCCD": "",
                       "MRCDE": "",
                       "OSTAT": "",
                       "RSTATS": "",
                       "DATEC": "",
                       "TIME": ts,
                       "RTYPE": "",
                       "NET#": "",
                       "READAT": "",
                       "UCHAR": "",
                       "MANUFR": "",
                       "ACTINA": "",
                       "TMETER": "",
                       "FAIL": "",
                       "PREAD": "",
                       "PRDAT": "",
                       "DISP11": read_data["Premise Detail"]["Address 1"],
                       "DISP12": read_data["Premises Notes"]["Special Instruction 2"],
                       "DISP13": "",
                       "DISP14": "",
                       "DISP21": "",
                       "DISP22": "",
                       "DISP23": "",
                       "DISP24": "",
                       "DISP25": "",
                       "DISP26": read_data["Premise Detail"]["Customer Name"],
                       "DISP27": read_data["Premises Notes"]["Special Instruction"],
                       "DISP28": "",
                       "FUTURE": "",
                       "UFIEL": read_data["Premise Detail"]["Account Number"],
                       "DAYSZR": read_data["Read Detail"]["Days of No Flow"],
                       "REVFLR": read_data["Read Detail"]["Reverse Flow"],
                       "DAYSLK": read_data["Read Detail"]["Days of consumption"],
                       "LKSTAT": read_data["Read Detail"]["Consumption Flag"]}
                    
                _row = []
                for k, v in row.items():
                    _row.append(self.pad_elm_to_as400_len(k, v))
                _lines.append("".join(elm for elm in _row))
        
        print(_lines[1])
        with open ("Sample_Radio_File.txt", "w") as outfp:
            for l in _lines:
                outfp.write(l)


    def pad_elm_to_as400_len(self, k, v):

        buffer_lens = {"ROUTE": 10,
                       "WALK": 4,
                       "PAGN": 4,
                       "RESQ": 2,
                       "HHELD": 6,
                       "RDIR": 1,
                       "NDIAL": 1,
                       "IDEXP": 13,
                       "IDCAP": 13,
                       "IDOVR": 13,
                       "DECI": 1,
                       "MREAD": 10,
                       "READO": 10,
                       "HIGHR": 10,
                       "LOWR": 10,
                       "DTER": 6,
                       "DTEE": 6,
                       "NOTES": 8,
                       "LOCCD": 2,
                       "MRCDE": 2,
                       "OSTAT": 2,
                       "RSTATS": 1,
                       "DATEC": 6,
                       "TIME": 6,
                       "RTYPE": 1,
                       "NET#": 2,
                       "READAT": 1,
                       "UCHAR": 7,
                       "MANUFR": 1,
                       "ACTINA": 1,
                       "TMETER": 1,
                       "FAIL": 1,
                       "PREAD": 10,
                       "PRDAT": 6,
                       "DISP11": 24,
                       "DISP12": 24,
                       "DISP13": 24,
                       "DISP14": 24,
                       "DISP21": 24,
                       "DISP22": 24,
                       "DISP23": 24,
                       "DISP24": 24,
                       "DISP25": 24,
                       "DISP26": 24,
                       "DISP27": 24,
                       "DISP28": 24,
                       "FUTURE": 1,
                       "UFIEL": 40,
                       "DAYSZR": 1,
                       "REVFLR": 1,
                       "DAYSLK": 1,
                       "LKSTAT": 1}

        if len(str(v)) > buffer_lens[k]:
            return str(v)[:buffer_lens[k]].replace("\n", "")
        else:
            padding = "".join([" " for x in range(buffer_lens[k] - len(str(v)))])
            return f"{v}{padding}".replace("\n", "")

if __name__ == "__main__":
    parser = V4Parser("./sample_data/tjg_route_1.txt")
    parser.parse_json_to_radio()