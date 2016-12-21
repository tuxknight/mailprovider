# -*- coding:utf-8 -*-
# Author: Chufuyuan
# Date: 16/11/4

import csv
import datetime
import functools
import logging.handlers
import smtplib
import sqlite3
import sys
from email.header import Header
from email.mime.text import MIMEText

import os
from flask import Flask, request, jsonify, make_response, Response, Blueprint

__doc__ = """
Mail provider for open-falcon
curl -X POST http://127.0.0.1:9988 -d "content=xxx&tos=abc@example.com,user@example.com&subject=xxx"
"""

CONFIG = {
    "log_file": "./var/app.log",
    "smtp_server": "smtp.example.com",
    "login_name": "alert@example.com",
    "login_pass": "AvEry5ecurE%ecRet",
    "deploy_info_path": "./",
    "deploy_info_file": "deploy_info.csv",
    "http_name": "auth_name",
    "http_pass": "pa55w0rdN0teMPty",
    "sqlite3_db_file": "./deploy_info.db",
    "table_name": "deployment"
}

sqls = {"drop_table": "DROP TABLE IF EXISTS %s" % CONFIG.get("table_name", "deployment"),
        "create_table": "CREATE TABLE IF NOT EXISTS %s "
                        "(id integer PRIMARY KEY, datetime text, target_host text, "
                        "project text, app_name text, deploy_host text,user text, "
                        "delivered text)" % CONFIG.get("table_name", "deployment"),
        "insert_table": "INSERT INTO %s (datetime, target_host, project, app_name, "
                        "deploy_host, user, delivered) VALUES (?,?,?,?,?,?,?)" % CONFIG.get("table_name", "deployment"),
        "select_undelivered": "SELECT * FROM %s WHERE delivered='0'" % CONFIG.get("table_name", "deployment")
        }

fmt = "%(name)s %(levelname)s %(asctime)s " \
      "[%(module)s(%(process)s):%(lineno)s:%(funcName)s] %(message)s"

formatter = logging.Formatter(fmt)
# logging into files
rotation_handler = logging.handlers.RotatingFileHandler(CONFIG.get("log_file", "./app.log"),
                                                        maxBytes=5 * 1024 * 1024 * 1024,
                                                        backupCount=5)
rotation_handler.setFormatter(formatter)
rotation_handler.setLevel(logging.DEBUG)

# logging into stdout
std_handler = logging.StreamHandler(sys.stdout)
std_handler.setFormatter(formatter)
std_handler.setLevel(logging.DEBUG)

applogger = logging.getLogger("app")
applogger.setLevel(logging.DEBUG)
applogger.addHandler(rotation_handler)
applogger.addHandler(std_handler)

CONFIG["logger"] = applogger


def timer(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        kw = [(k, v) for k, v in kwargs.iteritems() if kwargs and k != "msg"]
        if args:
            kw.extend(list(args))
        applogger.debug("%s(%s)" % (func.__name__, kw))
        start = datetime.datetime.now()
        ret = func(*args, **kwargs)
        end = datetime.datetime.now()
        time_cost = end - start
        applogger.info("[%s timecost](%s)" % (func.__name__, time_cost))
        return ret
    return wrapper


def check_auth(auth_config, username, password):
    return username == auth_config.get("http_name") and password == auth_config.get("http_pass")


def authenticate():
    return Response('Could not verify your access request.\n'
                    'You have to login', 401,
                    {'WWW-Authenticate': 'Basic realm="Login Required"'})


def requires_auth(user_config):  # 装饰器传入 flask app 用于读取 app.config 里面的用户名 密码
    def _requires_auth(func):
        @functools.wraps(func)
        def decorated(*args, **kwargs):
            auth = request.authorization
            if not auth or not check_auth(user_config, auth.username, auth.password):
                return authenticate()
            return func(*args, **kwargs)
        return decorated
    return _requires_auth


app = Flask(__name__)
app.config.update(CONFIG)

db_bp = Blueprint("db_bp", __name__)


@app.route("/", methods=["POST"])
@app.route("/mail", methods=["POST"])
@timer
def mail():
    # request_data = request.get_data(parse_form_data=True)
    _form_data = [request.form.get("content", ""), request.form.get("tos", ""), request.form.get("subject", "")]
    _form_keys = ["content", "tos", "subject"]

    request_data = "&".join(["=".join(pair) for pair in zip(_form_keys, _form_data)])

    # applogger.info("request_data(%s)" % "&".join(["=".join(pair) for pair in zip(_form_keys, _form_data)]))
    applogger.info("request_data(%s)" % "&".join(["=".join(pair) for pair in zip(_form_keys[1:], _form_data)[1:]]))
    # MIMEText object
    email = write_email(toaddrs=request.form.get("tos", ""), subject=request.form.get("subject", ""),
                        msg=request.form.get("content", ""))
    send_email(toaddrs=request.form.get("tos", ""), msg=email)
    return jsonify(request_data)


@timer
def write_email(toaddrs, subject, msg):
    email = MIMEText(msg, 'plain', 'utf-8')
    email["From"] = CONFIG.get("login_name")
    email["To"] = toaddrs
    email["Subject"] = Header(subject, 'utf-8').encode()
    return email


@timer
def send_email(toaddrs, msg):
    server = smtplib.SMTP(host=CONFIG.get("smtp_server"))
    # server = smtplib.SMTP_SSL(host=CONFIG.get("smtp_server"))
    # server.set_debuglevel(1)
    server.login(CONFIG.get("login_name"), CONFIG.get("login_pass"))
    server.sendmail(CONFIG.get("login_name"), toaddrs.split(","), msg.as_string())
    server.close()


@app.route("/deployInfo", methods=["POST"])
@requires_auth(app.config)
@timer
def deploy_info():
    # write deploy information to a local csv file
    # date time target_host project     app_name deploy_host user
    args = request.get_json()
    ret = []
    filepath = os.path.join(app.config.get("deploy_info_path"), app.config.get("deploy_info_file"))
    if args:
        date = args.get("date")
        time = args.get("time")
        target_host = args.get("target_host")
        project = args.get("project")
        app_name = args.get("app_name")
        deploy_host = args.get("deploy_host")
        user = args.get("user")
        ret = [" ".join([date, time]), target_host, project, app_name, deploy_host, user]
    try:
        return make_response("OK") if append_deploy_info(ret, filepath) else make_response("Failed")
    except Exception as e:
        applogger.error(e)
        return make_response("Exception", 500)


@timer
def append_deploy_info(line, csv_filepath):
    line = [x.encode("utf-8") for x in line]
    if not os.path.exists(csv_filepath):
        applogger.info("trying to create %s" % csv_filepath)
        os.system("touch %s" % csv_filepath)
    with open(csv_filepath, 'ab') as f:
        csv_writer = csv.writer(f, delimiter='\t')
        try:
            csv_writer.writerow(line)
        except Exception as e:
            applogger.error(e)
            return False
    return True


def init_db(db_filepath):
    try:
        with sqlite3.connect(db_filepath) as db_con:
            db_con.execute(sqls.get("create_table"))
            return db_con
    except Exception as e:
        applogger.error(e)
        db_con.close() if db_con else False
        return None


@db_bp.route("/deployInfo", methods=["POST"])
@requires_auth(app.config)
@timer
def db_deploy_info():
    # write deploy information to sqlite3 database
    # date time target_host project app_name deploy_host user delivered[1=noticed 0=unnoticed]
    args = request.get_json()
    ret = []
    if args:
        date = args.get("date")
        time = args.get("time")
        target_host = args.get("target_host")
        project = args.get("project").encode("utf-8")
        app_name = args.get("app_name")
        deploy_host = args.get("deploy_host")
        user = args.get("user")
        ret = [" ".join([date, time]), target_host, project, app_name, deploy_host, user]
        ret = [x.decode("utf-8") for x in ret]
    try:
        db_con = init_db(db_filepath=app.config.get("sqlite3_db_file", "./sqlite3.db"))  # init and create table
    except Exception as e:
        applogger.error(e)
        return make_response("Exception")
    try:
        if db_append_deploy_info_(ret, db_con):
            return make_response("OK", 200)
        else:
            return make_response("Failed", 500)
    except Exception as e:
        applogger.error(e)
        return make_response("Exception", 500)


@timer
def db_append_deploy_info_(line, db_con):
    line.extend('0')  # add a column [delivered]
    with db_con:
        cur = db_con.cursor()
        try:
            cur.execute(sqls.get("insert_table"), line)
            db_con.commit()
        except Exception as e:
            applogger.error(e)
            cur.close()
            return False
        else:
            return True


@db_bp.route("/notice", methods=["POST"])
@requires_auth(app.config)
@timer
def send_notice():
    tos = request.form.get("tos", "")  # 收件人
    subject = "发布情况"
    head_line = "发布时间\t目标主机\t业务系统\t项目名称\t发布机\t发布用户\n"
    try:
        # init and create table if not exists
        db_con = init_db(db_filepath=app.config.get("sqlite3_db_file", "./sqlite3.db"))
        db_con.row_factory = sqlite3.Row
    except Exception as e:
        applogger.error(e)
        return make_response("Exception")

    # select undelivered records and send email
    sms_content = []
    ids = []
    with db_con:
        for row in db_con.execute("SELECT * FROM %s WHERE delivered='0'" % app.config.get("table_name", "deployment")):
            deploy_record = [row["datetime"], row["target_host"], row["project"], row["app_name"], row["deploy_host"],
                             row["user"]]
            sms_content.append(deploy_record)
            ids.append(str(row["id"]))
        sms_content = [item.encode("utf-8") for row in sms_content for item in row]
    data_line = []
    for row_id in range(0, len(sms_content) / 6):  # 0 6 12 18 24
        row = sms_content[row_id * 6:row_id * 6 + 6]
        data_line.append("\t".join(row))
    sms_content = head_line + "\n".join(data_line)

    if not ids:  # 未发现待推送数据
        return make_response('OK', 304)
    if ids:  # 存在未推送的数据
        try:
            mail = write_email(toaddrs=tos, subject=subject, msg=sms_content)
            applogger.info("sending email")
            send_email(toaddrs=tos, msg=mail)
        except Exception as e:
            db_con.close()
            applogger.error(e)
            return make_response("Exception", 500)
        else:  # 邮件发送成功, 将数据标记为已推送
            try:
                with db_con:
                    db_con.execute("UPDATE %s SET delivered = '1' WHERE id in (%s)" % (
                    app.config.get("table_name"), ",".join(ids)))
                    db_con.commit()
            except Exception as e:
                applogger.error(e)
                return make_response("Exception", 500)
            else:
                return make_response('OK', 202)


@db_bp.route("/list", methods=["GET"])
@requires_auth(app.config)
def list_records():
    content = ""
    ids = []
    try:
        # init and create table if not exists
        db_con = init_db(db_filepath=app.config.get("sqlite3_db_file", "./sqlite3.db"))
        db_con.row_factory = sqlite3.Row
    except Exception as e:
        applogger.error(e)
        return make_response("Exception", 500)

    # select undelivered records and send email
    with db_con:
        for row in db_con.execute("SELECT * FROM %s" % app.config.get("table_name", "deployment")):
            line = "&nbsp;&nbsp;".join([str(row["id"]), row["datetime"], row["target_host"], row["project"],
                                        row["app_name"], row["deploy_host"], row["user"], row["delivered"]])
            content = "<br />".join([content, line])
            ids.append(row["id"])
    return make_response(content)


app.register_blueprint(db_bp, url_prefix="/db")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8088, debug=True)
