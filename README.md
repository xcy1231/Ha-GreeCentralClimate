# Ha-GreeCentralClimate
格力中央空调Homeassistant插件，使用格力云控进行控制


gree2目录复制到custom_components，再在configuration.yaml中加上配置：

```
climate:
  - platform: gree2
```

使用scan_interval可以自定义同步时间：
```
climate:
  - platform: gree2
    scan_interval: 20
```

使用temp_step可以自定义温度调整精度,默认为1,需要支持0.5可以在这里设置：
```
climate:
  - platform: gree2
    temp_step: 0.5
```

## 最新修改,集成[Fake-Gree-server](https://github.com/markv9401/Fake-Gree-server),通过该server进行云控的状态获取与控制

原因是重启HA后云控经常不响应，抓包猜测格力的云控会通过TCP直连格力的云服务器，格力APP会通过服务器来进行状态获取与控制，云控仅在重置后第一次或与服务器断连后能够直接响应本地UDP请求，但直接断开云控的外网权限会造成一段时间后云控失去任何响应，所以需要在本地伪造一个格力的云服务器，保持云控可用，同时也可通过该伪造服务器进行状态获取与控制

需要在配置中增加一行配置```fake_server```，即可启动fake server，同时需要在内网将```dis.gree.com```域名指向fake server的ip，也即HA服务器的ip，这里没有使用自动获取本机ip的方式，主要是麻烦，各种不同安装方式网卡选择等会导致获取的ip不对，```dis.gree.com```也即云控会默认连接的格力服务器域名:
```
climate:
  - platform: gree2
    fake_server: 192.168.1.110
```

多个云控可以增加多个配置，不过需要事先从路由器里拿到云控的ip，fake_server也仅需配置一个即可：

```
climate:
  - platform: gree2
    host: 192.168.1.100
    scan_interval: 20
    fake_server: 192.168.1.110
  - platform: gree2
    host: 192.168.1.101
    scan_interval: 20
```

由于无法通过云控获得空调内置传感器温度，原本写死26度，现支持引入其他温度传感器展示到空调面板:

```
climate:
  - platform: gree2
    temp_sensor:
       climate_mac_1: sensor_entity_id_1
       climate_mac_2: sensor_entity_id_2
```

```climate_mac``` 为空调名称格力空调后的一串字母数字，做过名称自定义的可能看不到，但是可以找到空调实体ID的最后一段，```sensor_entity```为温度传感器的实体ID```entity_id```

<center>
	<img src="./climate-mac-1.jpg" width="300"/>
	<img src="./climate-mac-2.jpg" width="300"/>
</center>

配置文件configuration.yaml增加日志配置可获取相对详细的日志打印，有问题可以提供下日志方便查看：

```
logger:
  default: warning
  logs:
    custom_components.gree2: debug
    custom_components.gree2.climate: debug
```

效果图：
![image](./ha-gree.jpg)

# 参考
[Fake-Gree-server](https://github.com/markv9401/Fake-Gree-server)

[gree-hvac-mqtt-bridge](https://github.com/arthurkrupa/gree-hvac-mqtt-bridge)

[HomeAssistant-GreeClimateComponent](https://github.com/RobHofmann/HomeAssistant-GreeClimateComponent)

[[插件发布] [5月6日更新]带反馈的WIFI空调](https://bbs.hassbian.com/forum.php?mod=viewthread&tid=3651)
