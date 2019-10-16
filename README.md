# zabbix-ibm-storwize
Python script for monitoring IBM Storwize storages


In template "Template EMC Unity REST-API" in section "Macros" need set these macros:
- {$STORWIZE_USER}
- {$STORWIZE_PASSWORD}
- {$STORWIZE_PORT}

In agent configuration file, **/etc/zabbix/zabbix_agentd.conf** must be set parameter **ServerActive=xxx.xxx.xxx.xxx**

- In Linux-console need run this command to make discovery. Script must return value 0 in case of success.
```bash
./storwize_get_state.py  --storwize_ip=xxx.xx.xx.xxx --storwize_port=22 --storwize_user=user_name_of_storagedevice --storwize_password='password' --storage_name="storage_name_in_zabbix" --discovery
```
- On zabbix proxy or on zabbix servers need run **zabbix_proxy -R config_cache_reload** (zabbix_server -R config_cache_reload)

- In Linux-console need run this command to get value of metrics. Scripts must return value 0 in case of success.
```bash
./storwize_get_state.py  --storwize_ip=xxx.xx.xx.xxx --storwize_port=22 --storwize_user=user_name_of_storagedevice --storwize_password='password' --storage_name="storage_name_in_zabbix" --status
```
If you have executed this script from console from user root or from another user, please check access permission on file **/tmp/storwize_state.log**. It must be allow read, write to user zabbix.
