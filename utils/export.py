import config

def get_month_name(month):
    for name, num in config.MONTH_NAMES.items():
        if num == month and (len(name) > 3 or name.lower() == 'май'):
            return name
    return str(month)