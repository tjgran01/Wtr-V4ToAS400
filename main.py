import json

def get_cols():

    with open ("./data/RADIO_EOD_8-9.csv") as inf:
        header = inf.readline()[1:].replace("\n", "")
        
        in_quote = False
        replaced = []
        for char in inf.readline()[2:]:
            if char == '"':
                if in_quote:
                    in_quote = False
                else:
                    in_quote = True

            if char == ",":
                if in_quote:
                    replaced.append("-")
                else:
                    replaced.append(char)
            else:
                replaced.append(char)

    col_names = header.split(",")[:-2]
    data_cells = "".join(replaced).split(",")[:-2]

    to_return = {}
    for i, col_name in enumerate(col_names):
        has_data = True if len(data_cells[i].strip()) > 0 else False
        to_return[col_name] = {"Position": i,
                               "HasData": has_data,
                               "ColLen": len(data_cells[i])}
        
    return to_return


def main():

    cols = get_cols()
    with open("./out.json", "w") as outf:
        json.dump(cols, outf, indent=4)


if __name__ == "__main__":
    main()