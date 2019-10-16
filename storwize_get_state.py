#!/bin/python
# -*- coding: utf-8 -*-

import os
import time
import argparse
import sys
import json
import subprocess
import paramiko
import logging
import logging.handlers
import csv
import re


# Create log-object
LOG_FILENAME = "/tmp/storwize_state.log"
# sys.argv[5] contain this string "--storage_name=<storage_name_in_zabbix>". List slicing delete this part "--storage_name="
STORAGE_NAME = sys.argv[5][15:]
storwize_logger = logging.getLogger("storwize_logger")
storwize_logger.setLevel(logging.INFO)

# Set handler
storwize_handler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=(1024**2)*10, backupCount=5)
storwize_formatter = logging.Formatter('{0} - %(asctime)s - %(name)s - %(levelname)s - %(message)s'.format(STORAGE_NAME))

# Set formatter for handler
storwize_handler.setFormatter(storwize_formatter)

# Add handler to log-object
storwize_logger.addHandler(storwize_handler)



def storwize_connect(storwize_user, storwize_password, storwize_ip, storwize_port):
	try:
		ssh_client = paramiko.SSHClient()
		ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		ssh_client.connect(hostname=storwize_ip, username=storwize_user, password=storwize_password, port=22)
		storwize_logger.info("Connection Established Successfully")
		return ssh_client
	except Exception as oops:
		storwize_logger.info("Connection Close Error Occurs: {0}".format(oops))
		sys.exit("1000")



def storwize_logout(ssh_client):
	try:
		ssh_client.close()
		storwize_logger.info("Connection Closed Successfully")
	except Exception as oops:
		storwize_logger.info("Connection Close  Error Occurs: {0}".format(oops))
		sys.exit("1000")



def convert_to_zabbix_json(data):
        output = json.dumps({"data": data}, indent = None, separators = (',',': '))
        return output



def convert_text_to_numeric(value):
	if value == 'online':
		numericValue = 0
	elif value == 'offline':
		numericValue = 1
	elif value == 'degraded':
		numericValue = 2
	elif value == 'active':
		numericValue = 3
	elif value == 'inactive_configured':
		numericValue = 4
	elif value == 'inactive_unconfigured':
		numericValue = 5
	elif value == 'offline_unconfigured':
		numericValue = 6
	elif value == 'excluded':
		numericValue = 7
	elif value == 'on':
		numericValue = 8
	elif value == 'off':
		numericValue = 9
	elif value == 'slow_flashing':
		numericValue = 10
	elif value == 'degraded_paths':
		numericValue = 11
	elif value == 'degraded_ports':
		numericValue = 12
	else:
		numericValue = 100

	return numericValue



def advanced_info_of_resource(resource, needed_attributes, storwize_connection, *id_of_resource):

	""" needed_attributes - list of parameters, that we wont to get
	    id_of_resource - list of additional parameters, that uniquely determine resource.
	    Example: for PSU - first element of list is enclosure_id, secondary element of list is PSU_id"""


	if resource == 'lsenclosure':
		stdin, stdout, stderr = storwize_connection.exec_command('svcinfo {0} {1}'.format(resource, id_of_resource[0]))
	elif resource == 'lsenclosurepsu':
		stdin, stdout, stderr = storwize_connection.exec_command('svcinfo {0} -psu {1} {2}'.format(resource, id_of_resource[1], id_of_resource[0]))

	if len(stderr.read()) > 0:
		storwize_logger.info("Error Occurs in advanced info of enclosure - {0}".format(stderr.read()))
		storwize_logout(storwize_connection)
		sys.exit("1100")
	else:
		attributes_of_resource = stdout.read() # Получили расширенные атрибуты в виде строки (variable contain advanced attributes in string)
		dict_of_attributes = {} # Здесь будут храниться расширенные атрибуты ресурса в формате ключ-значение (will contain advanced attributes in key-value)
		try:
			for attribute in attributes_of_resource.split('\n'): # Разделил строку и получили список из расшренные атрибутов
				if len(attribute) > 0:
					temp = attribute.split(' ')
					dict_of_attributes[temp[0]] = temp[1]
		except Exception as oops:
			storwize_logger.error("Error occures in function advanced_info_of_resource - {0}".format(oops))
			storwize_logout(storwize_connection)
			sys.exit("1100")

	# Создаем словарь из необходимых нам свойств ресурса (create dictionary that contain properies of resource)
	result = {}
	for each_value in needed_attributes:
		result[each_value] = dict_of_attributes[each_value]

	return result


def convert_capacity_to_bytes(capacity_in_string):
	""" Конвертирует значение, которое отдает СХД в виде строки, в байты
        Convert value, from string to byte, that get from storage device
    """

	convert_to_bytes = {'TB':1024**4, 'GB':1024**3, 'MB':1024**2, 'KB':1024}
	try:
		list_of_capacity = re.search('([\d\.]+)([\D]+)',capacity_in_string) # Ищем по регулярному выражению и находим две группы совпадения
		converted_capacity = float(list_of_capacity.group(1)) * convert_to_bytes[list_of_capacity.group(2)]
		return int(converted_capacity) # Конвертация в целые числа, потому что для float в заббиксе есть ограничение (convert to type ineger)
	except Exception as oops:
		storwize_logger.error("Error occurs in converting capactity_in_string to capactiy_in_bytes".format(oops))



def send_data_to_zabbix(zabbix_data, storage_name):
	sender_command = "/usr/bin/zabbix_sender"
	config_path = "/etc/zabbix/zabbix_agentd.conf"
	time_of_create_file = int(time.time())
	temp_file = "/tmp/{0}_{1}.tmp".format(storage_name, time_of_create_file)

	with open(temp_file, "w") as f:
		f.write("")
		f.write("\n".join(zabbix_data))

	send_code = subprocess.call([sender_command, "-vv", "-c", config_path, "-s", storage_name, "-T", "-i", temp_file], stdout = subprocess.PIPE, stderr = subprocess.PIPE)
	os.remove(temp_file)
	return send_code




def discovering_resources(storwize_user, storwize_password, storwize_ip, storwize_port, storage_name, list_resources):
	storwize_connection = storwize_connect(storwize_user, storwize_password, storwize_ip, storwize_port)

	xer = []
	try:
		for resource in list_resources:
			stdin, stdout, stderr = storwize_connection.exec_command('svcinfo {0} -delim :'.format(resource))

			if len(stderr.read()) > 0: # Если случились ошибки, запиши их в лог и выйди из скрипта (If errors occur, than write them to log and correctyl end of ssh-session)
				storwize_logger.info("Error Occurs in SSH Command - {0}".format(stderr.read()))
				storwize_logout(storwize_connection)
				sys.exit("1100")
			else:
				resource_in_csv = csv.DictReader(stdout, delimiter = ':') # Create CSV

				discovered_resource = []
				storwize_logger.info("Starting discovering resource - {0}".format(resource))
				for one_object in resource_in_csv:
					if ['lsvdisk', 'lsmdisk', 'lsmdiskgrp'].count(resource) == 1:
						one_object_list = {}
						one_object_list["{#ID}"] = one_object["id"]
						one_object_list["{#NAME}"] = one_object["name"] 
						discovered_resource.append(one_object_list)
					elif ['lsenclosurebattery', 'lsenclosurepsu', 'lsenclosurecanister'].count(resource) == 1:
						one_object_list = {}
						one_object_list["{#ENCLOSURE_ID}"] = one_object["enclosure_id"]
						if resource == 'lsenclosurebattery':
							one_object_list["{#BATTERY_ID}"] = one_object["battery_id"]
						if resource == 'lsenclosurepsu':
							one_object_list["{#PSU_ID}"] = one_object["PSU_id"]
						if resource == 'lsenclosurecanister':
							one_object_list["{#CANISTER_ID}"] = one_object["canister_id"]
						discovered_resource.append(one_object_list)
					elif ['lsportfc', 'lsportsas'].count(resource) == 1:
						one_object_list = {}
						one_object_list["{#PORT_ID}"] = one_object["port_id"]
						one_object_list["{#NODE_NAME}"] = one_object["node_name"]
						discovered_resource.append(one_object_list)
					elif ['lsenclosure'].count(resource) == 1:
						one_object_list = {}
						one_object_list["{#ID}"] = one_object["id"]
						one_object_list["{#MTM}"] = one_object["product_MTM"]
						one_object_list["{#SERIAL_NUMBER}"] = one_object["serial_number"]
						discovered_resource.append(one_object_list)
					elif ['lsdrive'].count(resource) == 1:
						one_object_list = {}
						one_object_list["{#ENCLOSURE_ID}"] = one_object["enclosure_id"]
						one_object_list["{#SLOT_ID}"] = one_object["slot_id"]
						discovered_resource.append(one_object_list)
					else:
						one_object_list = {}
						one_object_list["{#ID}"] = one_object["id"]
						one_object_list["{#ENCLOSURE_ID}"] = one_object["enclosure_id"]
						discovered_resource.append(one_object_list)

				storwize_logger.info("Succes get resource - {0}".format(resource))

				converted_resource = convert_to_zabbix_json(discovered_resource)
				timestampnow = int(time.time())
				xer.append("%s %s %s %s" % (storage_name, resource, timestampnow, converted_resource))
	except Exception as oops:
		storwize_logger.error("Error occurs in discovering - {0}".format(oops))
		storwize_logout(storwize_connection)
                sys.exit("1100")
		
	storwize_logout(storwize_connection)
	return send_data_to_zabbix(xer, storage_name)



def get_status_resources(storwize_user, storwize_password, storwize_ip, storwize_port, storage_name, list_resources):
	storwize_connection = storwize_connect(storwize_user, storwize_password, storwize_ip, storwize_port)

	state_resources = [] # В этот список будут складываться состояние каждого ресурса (диск, блок питания, ...) в формате zabbix (This list will contain state of every resource (disk, psu, ...) on zabbix format)
	is_there_expansion_enclosure = 0

	try:
		for resource in list_resources:
			stdin, stdout, stderr = storwize_connection.exec_command('svcinfo {0} -delim :'.format(resource))

			if len(stderr.read()) > 0: # Если случились ошибки, запиши их в лог и выйди из скрипта (If errors occur, then write them to log-file and correctyly end of ssh-session)
				storwize_logger.error("Error Occurs in SSH Command - {0}".format(stderr.read()))
				storwize_logout(storwize_connection)
				sys.exit("1100")
			else:
				resource_in_csv = csv.DictReader(stdout, delimiter = ':') # Create CSV
				timestampnow = int(time.time())
				storwize_logger.info("Starting collecting status of resource - {0}".format(resource))

				for one_object in resource_in_csv:
					if ['lsmdiskgrp'].count(resource) == 1:
						key_health = "health.{0}.[{1}]".format(resource, one_object["name"])
						key_overallocation = "overallocation.{0}.[{1}]".format(resource, one_object["name"])
						key_used = "used.{0}.[{1}]".format(resource, one_object["name"])
						key_virtual = "virtual.{0}.[{1}]".format(resource, one_object["name"])
						key_real = "real.{0}.[{1}]".format(resource, one_object["name"])
						key_free = "free.{0}.[{1}]".format(resource, one_object["name"])
						key_total = "total.{0}.[{1}]".format(resource, one_object["name"])

						state_resources.append("%s %s %s %s" % (storage_name, key_health, timestampnow, convert_text_to_numeric(one_object["status"])))
						state_resources.append("%s %s %s %s" % (storage_name, key_overallocation, timestampnow, one_object["overallocation"]))
						state_resources.append("%s %s %s %s" % (storage_name, key_used, timestampnow, convert_capacity_to_bytes(one_object["used_capacity"])))
						state_resources.append("%s %s %s %s" % (storage_name, key_virtual, timestampnow, convert_capacity_to_bytes(one_object["virtual_capacity"])))
						state_resources.append("%s %s %s %s" % (storage_name, key_real, timestampnow, convert_capacity_to_bytes(one_object["real_capacity"])))
						state_resources.append("%s %s %s %s" % (storage_name, key_free, timestampnow, convert_capacity_to_bytes(one_object["free_capacity"])))
						state_resources.append("%s %s %s %s" % (storage_name, key_total, timestampnow, convert_capacity_to_bytes(one_object["capacity"])))

					elif ['lsenclosurecanister'].count(resource) == 1:
						key_health = "health.{0}.[{1}.{2}]".format(resource, one_object["enclosure_id"], one_object["canister_id"])
						state_resources.append("%s %s %s %s" % (storage_name, key_health, timestampnow, convert_text_to_numeric(one_object["status"])))
					elif ['lsenclosurebattery'].count(resource) == 1:
						key_health = "health.{0}.[{1}.{2}]".format(resource, one_object["enclosure_id"], one_object["battery_id"])
						state_resources.append("%s %s %s %s" % (storage_name, key_health, timestampnow, convert_text_to_numeric(one_object["status"])))
					elif ['lsdrive'].count(resource) == 1:
						key_health = "health.{0}.[{1}.{2}]".format(resource, one_object["enclosure_id"], one_object["slot_id"])
						state_resources.append("%s %s %s %s" % (storage_name, key_health, timestampnow, convert_text_to_numeric(one_object["status"])))
					elif ['lsenclosurepsu'].count(resource) == 1:
						needed_attributes = ['input_failed', 'output_failed', 'fan_failed']
						enclosure_id = one_object["enclosure_id"]
						psu_id = one_object["PSU_id"]
						advanced_info = advanced_info_of_resource(resource, needed_attributes, storwize_connection, enclosure_id, psu_id)
						
						key_input_failed = "inFailed.{0}.[{1}.{2}]".format(resource, one_object["enclosure_id"], one_object["PSU_id"])
						key_output_failed = "outFailed.{0}.[{1}.{2}]".format(resource, one_object["enclosure_id"], one_object["PSU_id"])
						key_fan_failed = "fanFailed.{0}.[{1}.{2}]".format(resource, one_object["enclosure_id"], one_object["PSU_id"])
						key_health = "health.{0}.[{1}.{2}]".format(resource, one_object["enclosure_id"], one_object["PSU_id"])
						state_resources.append("%s %s %s %s" % (storage_name, key_health, timestampnow, convert_text_to_numeric(one_object["status"])))
						state_resources.append("%s %s %s %s" % (storage_name, key_input_failed, timestampnow, convert_text_to_numeric(advanced_info["input_failed"])))
						state_resources.append("%s %s %s %s" % (storage_name, key_output_failed, timestampnow, convert_text_to_numeric(advanced_info["output_failed"])))
						state_resources.append("%s %s %s %s" % (storage_name, key_fan_failed, timestampnow, convert_text_to_numeric(advanced_info["fan_failed"])))
					elif ['lsenclosure'].count(resource) == 1:
						needed_attributes = ['fault_LED']
						enclosure_id = one_object["id"]
						advanced_info = advanced_info_of_resource(resource, needed_attributes, storwize_connection, enclosure_id)

						key_fault_led = "faultLED.{0}.[{1}.{2}]".format(resource, one_object["id"], one_object["serial_number"])
						key_health = "health.{0}.[{1}.{2}]".format(resource, one_object["id"], one_object["serial_number"])
						state_resources.append("%s %s %s %s" % (storage_name, key_health, timestampnow, convert_text_to_numeric(one_object["status"])))
						state_resources.append("%s %s %s %s" % (storage_name, key_fault_led, timestampnow, convert_text_to_numeric(advanced_info["fault_LED"])))

						if one_object["type"] == "expansion":
							is_there_expansion_enclosure += 1

					elif ['lsportfc', 'lsportsas'].count(resource) == 1:
						key_running = "running.{0}.[{1}.{2}]".format(resource, one_object["port_id"], one_object["node_name"])
						state_resources.append("%s %s %s %s" % (storage_name, key_running, timestampnow, convert_text_to_numeric(one_object["status"])))
					elif ['lsvdisk', 'lsmdisk'].count(resource) == 1:
						key_health = "health.{0}.[{1}]".format(resource, one_object["name"])
						state_resources.append("%s %s %s %s" % (storage_name, key_health, timestampnow, convert_text_to_numeric(one_object["status"])))

				state_resources.append("%s %s %s %s" %(storage_name, "is_there_expansion_enclosure", timestampnow, is_there_expansion_enclosure))
	except Exception as pizdec:
		storwize_logger.error("Error occurs in collecting status - {}".format(pizdec))
		storwize_logout(storwize_connection) # Если возникло исключение, нужно корректно заверешить ssh-сессию (If exception occur, than correctly end of ssh-session)
		sys.exit("1100")

	storwize_logout(storwize_connection) # Завершаем ssh-сессию при успешном выполнении сбора метрик (Correctly end of session after get metrics)
	return send_data_to_zabbix(state_resources, storage_name)



def main():

        storwize_parser = argparse.ArgumentParser()
        storwize_parser.add_argument('--storwize_ip', action="store", help="Where to connect", required=True)
        storwize_parser.add_argument('--storwize_port', action="store", required=True)
        storwize_parser.add_argument('--storwize_user', action="store", required=True)
        storwize_parser.add_argument('--storwize_password', action="store", required=True)
        storwize_parser.add_argument('--storage_name', action="store", required=True)

        group = storwize_parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--discovery', action ='store_true')
        group.add_argument('--status', action='store_true')
        arguments = storwize_parser.parse_args()



        list_resources = ['lsvdisk', 'lsmdisk', 'lsmdiskgrp', 'lsenclosure', 'lsenclosurebattery', 'lsenclosurepsu', 'lsenclosurecanister', 'lsdrive', 'lsportfc', 'lsportsas']

        if arguments.discovery:
		storwize_logger.info("********************************* Starting Discovering *********************************")
                result_discovery = discovering_resources(arguments.storwize_user, arguments.storwize_password, arguments.storwize_ip, arguments.storwize_port, arguments.storage_name, list_resources)
                print result_discovery
        elif arguments.status:
		storwize_logger.info("********************************* Starting Get Status *********************************")
                result_status = get_status_resources(arguments.storwize_user, arguments.storwize_password, arguments.storwize_ip, arguments.storwize_port, arguments.storage_name, list_resources)
                print result_status


if __name__ == "__main__":
        main()
