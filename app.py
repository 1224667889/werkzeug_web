"""A simple URL shortener using Werkzeug and redis."""
import os

import redis
from jinja2 import Environment
from jinja2 import FileSystemLoader
from werkzeug.exceptions import HTTPException
from werkzeug.exceptions import NotFound
from werkzeug.middleware.shared_data import SharedDataMiddleware
from werkzeug.routing import Map
from werkzeug.routing import Rule
from werkzeug.urls import url_parse
from werkzeug.utils import redirect
from werkzeug.wrappers import Request
from werkzeug.wrappers import Response
from session import session

string_types = (str,)


def get_hostname(url):
    return url_parse(url).netloc


def _endpoint_from_view_func(view_func):
    assert view_func is not None, "expected view func if endpoint is not provided."
    return view_func.__name__


class Web:
    url_rule_class = Rule
    response_class = Response

    def __init__(self, config, session_path=".session\\"):
        self.session_path = session_path
        self.view_functions = {}
        self.secret_key = config.get('secret_key', os.urandom(24))
        # 配置redis
        self.redis = redis.Redis(config.get("redis_host", "localhost"), config.get("redis_port", 6379))
        template_path = os.path.join(os.path.dirname(__file__), "templates")
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_path), autoescape=True
        )
        self.jinja_env.filters["hostname"] = get_hostname
        # 路由空间
        self.url_map = Map(
            [
            ]
        )

    def render_template(self, template_name, **context):
        # 渲染模板
        t = self.jinja_env.get_template(template_name)
        return Response(t.render(context), mimetype="text/html")

    def dispatch_request(self, request):
        adapter = self.url_map.bind_to_environ(request.environ)
        try:
            endpoint, values = adapter.match()
            response = self.view_functions.get(f"{endpoint}")(request, **values)
            if isinstance(response, str):
                response = Response(response)
            return response
        except NotFound:
            return self.error_404()
        except HTTPException as e:
            print(e)
            return self.error_500()

    def wsgi_app(self, environ, start_response):
        request = Request(environ)
        response = self.dispatch_request(request)
        import hashlib
        m = hashlib.md5(request.remote_addr.encode())  # 先转成二进制，再加密
        value = m.hexdigest()
        response.set_cookie(key='session_id', value=value)
        return response(environ, start_response)

    def add_url_rule(self, rule, endpoint=None, view_func=None, **options):
        if endpoint is None:
            # 如果没有提供endpoint参数，则默认用view_func的名字
            endpoint = _endpoint_from_view_func(view_func)
        # 把endpoint参数添加到options里面
        options['endpoint'] = endpoint
        # 从options中pop出methods参数，并把值赋给methods变量，如果没有则置为None
        methods = options.pop('methods', None)
        # moehods的值为None的情况下
        if methods is None:
            # 如果view_func函数中有这个methods参数，则使用view_func中的。如果没有则赋一个列表('GET',)给methods
            methods = getattr(view_func, 'methods', None) or ('GET',)
        # 如果methods是字符串类型
        if isinstance(methods, string_types):
            # 抛出一个异常：methods需要是一个可以迭代的字符串
            raise TypeError('methods需要是一个可以迭代的字符串, '
                            '例: @app.route(..., methods=["POST"])')
        # 把methods里面的item都改成大写
        methods = set(item.upper() for item in methods)

        # 在view_func里面定义了一个属性required_methods = ()
        # 作用：用来定义一些必须的方法，配合provide_automatic_options使用
        required_methods = set(getattr(view_func, 'required_methods', ()))

        provide_automatic_options = getattr(view_func,
                                            'provide_automatic_options', None)

        # 判断provide_automati_options是否为None
        if provide_automatic_options is None:
            # 如果OPTIONS字符串没有在methods里面
            if 'OPTIONS' not in methods:
                # 则把provude_automatic_options改为True,并把OPTIONS添加到required_methods里面
                provide_automatic_options = True
                required_methods.add('OPTIONS')
            # 如果OPTIONS在methods里面，则把provide_automatic_options设置为False
            else:
                provide_automatic_options = False

        # 合并required_methods和methods这两个集合到methods里面
        methods |= required_methods

        # 创建路由规则
        # 调用url_rule_class方法，由于在Flask类的全局变量中定义了：url_rule_class = Rule, Rule是werkzeug/routing.py里面的一个类
        # 也就是相当于实例化了Rule得到了rule对象，具体实例化后的结果请看Rule源码分析
        rule = self.url_rule_class(rule, methods=methods, **options)
        # 把provide_automatic_options属性添加到rule对象里面
        rule.provide_automatic_options = provide_automatic_options

        # 在Flask类的__init__里面定义了self.url_map = Map(),Map是werkzeug/routing.py里面的一个类
        # self.url_map相当与实例化了Map,.add则是调用了Map类里面的add方法
        # 具体运行结果，请参考Map源码分析，以及Map源码中的add方法分析
        self.url_map.add(rule)
        # 如果提供了view_func
        if view_func is not None:
            # 在flask类的__init__里面定义了self.view_functions = {},
            # 从字典里面取endpoint值并赋值为old_func，（endpoint是传递的参数，默认为视图函数名）
            old_func = self.view_functions.get(endpoint)
            # 如果old_func有值，并且不等于view_func
            if old_func is not None and old_func != view_func:
                # 则抛出异常：视图函数映射被一个已经存在的函数名重写了
                # 也就是说已经存在了一个endpoint:old_func的映射，但是old_fun却不是view_func，也就是说endpoint重复了
                raise AssertionError('视图函数映射被一个已经存在的函数名重写了:'
                                     ' %s' % endpoint)
            # 添加视图函数与endpoint映射到view_functions字典里面
            self.view_functions[endpoint] = view_func

    def route(self, rule, **options):
        def decorator(f):
            endpoint = options.pop("endpoint", None)
            self.add_url_rule(rule, endpoint, f, **options)
            return f
        return decorator

    def error_500(self):
        response = self.render_template("500.html")
        response.status_code = 500
        return response

    def error_404(self):
        response = self.render_template("404.html")
        response.status_code = 404
        return response

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)

def create_app(config, with_static=True):
    # 创建app对象
    app = Web({"redis_host": config.get("redis_host", "localhost"),
               "redis_port": config.get("redis_port", 6379)})
    # 加载静态资源文件
    if with_static:
        app.wsgi_app = SharedDataMiddleware(
            app.wsgi_app, {"/static": os.path.join(os.path.dirname(__file__), "static")}
        )
    if not os.path.exists(app.session_path):
        os.mkdir(app.session_path)
    session.set_storage_path(app.session_path)
    session.load_local_session()
    return app


