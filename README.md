 mosquitto_pub -h localhost -t "traffic/emergency/4002" -m '{"emergency":"true"}'  
 mosquitto_pub -h localhost -t "signal/manual/4002" -m '{"set": true}'