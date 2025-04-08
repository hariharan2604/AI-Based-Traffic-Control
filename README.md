mosquitto_pub -h localhost -t "traffic/emergency/4002" -m '{"status":"start"}'  
mosquitto_pub -h localhost -t "traffic/emergency/4002" -m '{"status":"clear"}'  

mosquitto_pub -h localhost -t "signal/manual" -m '{"set": true}'
mosquitto_pub -h localhost -t "signal/manual" -m '{"set": false}'
