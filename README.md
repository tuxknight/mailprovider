# Quick Start

``mailprovider.py`` 根据 [open-falcon](http://open-falcon.org/) 组件 ``sender`` 预定义好的规范实现的一个简单的[邮件报警接口](https://book.open-falcon.org/zh/quick_install/judge_components.html).

部署同样遵循 ``open-falcon`` 各个组件的打包部署方式, 组织结构如下:

```
mailprovider
`+- env
 +- var
 +- control
 +- mailprovider.py
 +- gunicorn.conf
 +- wsgi.py
 +- requirements.txt
 +- install.sh
```

# 安装 & 启动

1. 执行安装脚本进行环境的初始化. 该脚本会在同级目录下创建一个 python 虚拟环境,并安装所需依赖.

    > sh install.sh

2. 执行控制脚本启动程序.

    > sh control start

# 使用

* ``open-falcon`` 的 ``sender`` 中配置

    > "mail": "http://ip_address:9988/mail"

* 脚本或人工调用

   > url=http://ip_address:9988/mail

   > curl -X POST $url -d "content=xxx&tos=user@example.com&subject=xxx"

# 附加功能

为帮助记录每天运维发布系统的频次,并定时自动邮件通知相关同事,增加了一些额外的接口. 对这类接口使用 HTTP Basic Authentication 做访问认证.

``POST /db/deployInfo``

参数 ``date`` ``time``  ``target_host``  ``project``  ``app_name``  ``deploy_host``  ``user``

该接口会保存发布记录到 sqlite 数据库中,并且带有是否已发送通知的标记.

``POST /db/notice``

参数 ``tos``

该接口会将库中所有未发送过通知的记录通过 ``/mail`` 接口发送出去,且标记为已发送.

PS 该脚本中还有一个  /deployInfo 接口为 /db/deployInfo 的原型,使用 csv 文件作为本地数据存储格式.并通过外部脚本实现发送通知功能.