 mosquitto_pub -h localhost -t "traffic/emergency/4002" -m '{"status":"start"}'  
 mosquitto_pub -h localhost -t "signal/manual/4002" -m '{"set": true}'