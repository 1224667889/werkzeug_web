from app import create_app
from app import session
# 设置项
config = {
    "redis_host": "localhost",
    "redis_port": 6379
}
# 创建app
app = create_app(config)


# 路由(需带request)
@app.route('/')
def index(request):
    # 返回模板，可进行参数传递
    return app.render_template('pure_str.html', text='123123123')


# 参数传递
@app.route('/<string:context>')
def context_example(request, context):
    # 直接返回内容
    return context


# session及请求方法设置
@app.route('/session', methods=['POST'])
def session_example(request):
    # 获取表单参数
    url = request.form["url"]
    print(url)

    # 新建/更改session(request, <int:储存位>, <string:内容>)(暂不支持使用名称储存)
    session.push(request, 0, 'xxx')
    # 获取指定位的session内容
    a = session.get(request, 0)
    print(a)
    # 删除指定位session
    session.pop(request, 0)

    import json
    # 返回request的json形式
    return json.dumps(request.form)


# session及请求方法设置
@app.route('/redis', methods=['POST'])
def redis_example(request):
    # redis添加(<string: key>, <value>)
    app.redis.append('xxx', 'yyy')
    # 删除
    a = app.redis.get('xxx')
    print(a)
    # 修改
    app.redis.delete('xxx')
    return 'success'

if __name__ == "__main__":
    # 启动
    from werkzeug.serving import run_simple
    run_simple("127.0.0.1", 5000, app, use_debugger=True, use_reloader=True)

