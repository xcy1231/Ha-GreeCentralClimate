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

效果图：
![image](./ha-gree.jpg)

# 参考
[gree-hvac-mqtt-bridge](https://github.com/arthurkrupa/gree-hvac-mqtt-bridge)

[HomeAssistant-GreeClimateComponent](https://github.com/RobHofmann/HomeAssistant-GreeClimateComponent)

[[插件发布] [5月6日更新]带反馈的WIFI空调](https://bbs.hassbian.com/forum.php?mod=viewthread&tid=3651)
