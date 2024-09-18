with open ("./sample_data/EZRoute.exp", "r") as infp:
    for line in infp.readlines():
        print(len(line))