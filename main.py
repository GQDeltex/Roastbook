#!./.venv/bin/python
# -*- coding: utf-8 -*-
"""
Python Backend for Roastbook
"""
import json
import hashlib
import socketio
import flask
import rethinkdb

CONFIG = {
    'host': 'localhost',
    'user': 'admin',
    'password': ''
}

SIO = socketio.Server()
APP = flask.Flask(__name__, static_folder="node_modules")
APP.wsgi_app = socketio.Middleware(SIO, APP.wsgi_app)
r = rethinkdb.RethinkDB()

with open('config.json', 'r') as f:
    CONFIG = json.loads(f.read())
    print("Read Configuration file")

try:
    print("Connecting to Database")
    CONNECTION = r.connect(host=CONFIG['host'],
                           user=CONFIG['user'],
                           password=CONFIG['password'],
                           db='roastbook')
except rethinkdb.errors.ReqlAuthError:
    print(
        "%s user is not existing, performing database setup" %
        CONFIG['user'])
    print("Connecting as default user")
    try:
        CONNECTION = r.connect(host=CONFIG['host'])
    except rethinkdb.errors.ReqlAuthError:
        print("Auto-Setup failed, couldn't log in as default user")
        print("Please set up the user, permission and tables yourself")
        exit()
    print("Creating User %s" % CONFIG['user'])
    r.db('rethinkdb').table('users').insert(
        {'id': CONFIG['user'], 'password': CONFIG['password']}).run(CONNECTION)
    print("Creating Database")
    r.db_create('roastbook').run(CONNECTION)
    print("Creating Tables and secondary indexes")
    r.db('roastbook').table_create('users').run(CONNECTION)
    r.db('roastbook').table_create('posts').run(CONNECTION)
    r.db('roastbook').table('users').index_create('username').run(CONNECTION)
    print("Setting up permissions")
    r.db('roastbook').grant(
        CONFIG['user'], {
            'read': True, 'write': True, 'config': False}).run(CONNECTION)
    try:
        print("Connecting with new user")
        CONNECTION = r.connect(
            host=CONFIG['host'],
            user=CONFIG['user'],
            password=CONFIG['password'],
            db='roastbook')
    except rethinkdb.errors.ReqlAuthError:
        print("New user didn't work, exiting...")
        exit()
print("Connected to Database!")
print(
    "host: %s, user: %s" %
    (CONFIG['host'],
     CONFIG['user']),
    CONNECTION.server())


@SIO.on('connect')
def connect(sid, environ):
    """
    SocketIO Event fired when a user connects
    """
    del environ  # delete environ because it is not used but given on function call
    print("connect ", sid)
    SIO.emit('post', data=r.db('roastbook').table('posts').order_by(
        r.desc('time')).limit(100).run(CONNECTION))
    SIO.emit('top_user', data=r.db('roastbook').table('users').order_by(
        r.desc('balance')).limit(5).pluck(['username', 'balance']).run(CONNECTION))
    SIO.emit('top_roast', data=r.db('roastbook').table('users').order_by(
        r.asc('balance')).limit(5).pluck(['username', 'balance']).run(CONNECTION))
    SIO.emit('all_names', data=r.db('roastbook').table('users').pluck(
        'username', 'id').coerce_to('array').run(CONNECTION))


@SIO.on('disconnect')
def disconnect(sid):
    """
    SocketIO Event fired when a user disconnects
    """
    print("disconnect ", sid)


@SIO.on('upvote')
def interactive_upvote(sid, environ=''):
    """
    SocketIO Event fires when users upvote
    """
    print("Interactive Upvote", sid, environ)
    vote(1, environ)


@SIO.on('downvote')
def interactive_downvote(sid, environ=''):
    """
    SocketIO Event fires when users downvote
    """
    print("Interactive Downvote", sid, environ)
    vote(-1, environ)


@APP.route("/")
def index():
    """
    flask.Flask Handler for Index Page
    """
    return flask.render_template("homepage.html")


@APP.route("/robots.txt")
def robots():
    """
    flask.Flask Handler for /robots.txt
    """
    return flask.send_file('./robots.txt')


@APP.route("/login", methods=["POST", "GET"])
def login():
    """
    flask.Flask Handler for the Login functionality
    Handles User Login for Normal POST and SocketIO
    """
    error = ""
    if flask.request.method == "POST":
        username = str(flask.Markup.escape(flask.request.form["username"]))
        password = str(flask.Markup.escape(flask.request.form["password"]))
        user_data = r.db('roastbook').table('users').get_all(
            username, index='username').coerce_to('array').run(CONNECTION)
        if not user_data:
            error = "Nutzer nicht gefunden!"
        else:
            data = user_data[0]
            pwd_hash = hashlib.sha256((username + password).encode()).hexdigest()
            #print ("ORIG:\t" + str(data['password']))
            #print ("NEW:\t" + str(pwd_hash))
            if data['password'] == pwd_hash:
                resp = flask.make_response(
                    flask.redirect(
                        flask.url_for(
                            "user",
                            username=username)))
                resp.set_cookie("user", value=username)
                resp.set_cookie("user_id", value=data['id'])
                return resp
            error = "Falsches Password."
    else:
        if flask.request.cookies.get("user"):
            resp = flask.make_response(flask.redirect(flask.url_for("index")))
            resp.set_cookie("user", value="")
            resp.set_cookie("user_id", value="")
            return resp
    return flask.render_template("login.html", error=error)


@APP.route("/register", methods=["POST", "GET"])
def register():
    """
    flask.Flask Handler for register route
    Handles registration process for normal POST and SocketIO
    """
    error = ""
    if flask.request.method == "POST":
        username = str(flask.Markup.escape(flask.request.form["username"]))
        password = str(flask.Markup.escape(flask.request.form["password"]))
        password_repeat = str(flask.Markup.escape(flask.request.form["password_repeat"]))
        if r.db('roastbook').table('users').filter(
                {'username': username}).count().run(CONNECTION) != 0:
            error = """Ein Benutzer mit deinem Benutzernamen existiert bereits,
             suche dir einen anderen aus."""
        elif password != password_repeat:
            error = "Die beiden eingegebenen Passwoerter stimmen nicht ueberein!"
        else:
            pwd_hash = hashlib.sha256((username + password).encode()).hexdigest()
            user_id = r.db('roastbook').table('users').insert(
                {
                    'username': username,
                    'password': pwd_hash,
                    'balance': 0,
                    'liked': []}).run(CONNECTION)['generated_keys'][0]
            print("New User: %s, id: %s" % (username, user_id))
            resp = flask.make_response(
                flask.redirect(
                    flask.url_for(
                        "user",
                        username=username)))
            resp.set_cookie("user", value=username)
            resp.set_cookie("user_id", value=user_id)
            return resp
    return flask.render_template("register.html", error=error)


@APP.route("/user/<username>")
def user(username):
    """
    flask.Flask Handler returns the User page with infos about a user
    """
    data = r.db('roastbook').table('users').get_all(
        username, index='username').coerce_to('array').run(CONNECTION)
    if data:
        return flask.render_template(
            "user.html",
            user=data[0],
            profile=data[0]['id'])
    return "Diesen Benutzer gibt es nicht!"


@APP.route("/edit_post/<post_id>", methods=["GET", "POST"])
def edit_post(post_id):
    """
    flask.Flask Handler for Page to edit Posts
    """
    data = r.db('roastbook').table('posts').get(post_id).run(CONNECTION)
    if flask.request.cookies.get("user_id") != data['from_id']:
        return "You are not allowed to do this!\r\n<a href='" + \
            flask.url_for('index') + "'>Back to Homepage</a>"
    if flask.request.method == "POST":
        text = str(flask.Markup.escape(flask.request.form['text']))
        r.db('roastbook').table('posts').get(
            post_id).update({'text': text}).run(CONNECTION)
        return flask.redirect(
            flask.url_for(
                'user',
                username=flask.request.cookies.get("user")))
    return flask.render_template("edit.html", data=data)


@APP.route("/upvote")
def upvote():
    """
    flask.Flask Handler to upvote
    """
    user_id = flask.request.cookies.get("user_id")
    if user_id == "":
        return "You are not allowed to do this!\r\n<a href='" + \
            flask.url_for('index') + "'>Back to Homepage</a>"
    post_id = flask.request.args.get("id")
    source = flask.request.args.get("source", default=flask.url_for("index"))
    vote(1, {'user_id': user_id, 'post_id': post_id})
    return flask.redirect(source)


@APP.route("/downvote")
def downvote():
    """
    flask.Flask Handler to downvote
    """
    user_id = flask.request.cookies.get("user_id")
    if user_id == "":
        return "You are not allowed to do this!\r\n<a href='" + \
            flask.url_for('index') + "'>Back to Homepage</a>"
    post_id = flask.request.args.get("id")
    source = flask.request.args.get("source", default=flask.url_for("index"))
    vote(-1, {'user_id': user_id, 'post_id': post_id})
    return flask.redirect(source)


def vote(amount, args):
    """
    Function used by flask.Flask Handlers and SocketIO Events
    to actually vote posts up/down
    """
    user_id = args['user_id']
    post_id = args['post_id']
    if user_id == '':
        return
    post = r.db('roastbook').table('posts').get(post_id).run(CONNECTION)
    post_author = r.db('roastbook').table(
        'users').get(post['from_id']).run(CONNECTION)
    post_liker = r.db('roastbook').table('users').get(user_id).run(CONNECTION)
    if post_liker['liked'] != []:
        if post_id in post_liker['liked']:
            print("Post already liked!")
            return
    else:
        post_liker['liked'] = []
    if amount > 0:
        post['upvote'] += amount
        post_author['balance'] += amount
    else:
        post['downvote'] += abs(amount)
        post_author['balance'] += amount
    if ((post['upvote'] + post['downvote']) !=
            0 and post['upvote'] != post['downvote']):
        post['up_perc'] = (float(post['upvote']) /
                           float(post['upvote'] + post['downvote'])) * 100
        post['down_perc'] = (float(post['downvote']) /
                             float(post['upvote'] + post['downvote'])) * 100
    else:
        post['up_perc'] = 50
        post['down_perc'] = 50
    print("Size before: ", post['up_perc'], post['down_perc'])
    min_perc = 15
    if post['up_perc'] < min_perc:
        post['up_perc'] = min_perc
        post['down_perc'] = 100 - min_perc
    if post['down_perc'] < min_perc:
        post['down_perc'] = min_perc
        post['up_perc'] = 100 - min_perc
    print("Size after: ", post['up_perc'], post['down_perc'])
    post_liker['liked'].append(post_id)
    #print (str(liked))
    print("%s liked post %s" % (post_liker['username'], post_id))
    r.db('roastbook').table('users').get(post_author['id']).update(
        {'balance': post_author['balance']}).run(CONNECTION)
    r.db('roastbook').table('users').get(user_id).update(
        {'liked': post_liker['liked']}).run(CONNECTION)
    r.db('roastbook').table('posts').get(post_id).update(post).run(CONNECTION)
    SIO.emit('post', data=r.db('roastbook').table('posts').order_by(
        r.desc('time')).limit(100).run(CONNECTION))
    SIO.emit('top_user', data=r.db('roastbook').table('users').order_by(
        r.desc('balance')).limit(5).pluck(['username', 'balance']).run(CONNECTION))
    SIO.emit('top_roast', data=r.db('roastbook').table('users').order_by(
        r.asc('balance')).limit(5).pluck(['username', 'balance']).run(CONNECTION))
    return


@APP.route("/newpost", methods=["POST"])
def newpost():
    """
    flask.Flask Handler for new Posts
    """
    text = str(flask.Markup.escape(flask.request.form['text']))
    user_id = flask.request.form['username']
    username = r.db('roastbook').table('users').get(
        user_id).pluck('username').run(CONNECTION)['username']
    print("Created Post:" + str(username))
    my_username = flask.request.cookies.get("user")
    my_user_id = flask.request.cookies.get("user_id")
    if r.db('roastbook').table('users').get(
            user_id).pluck('id').count().run(CONNECTION) == 1:
        r.db('roastbook').table('posts').insert(
            {
                'text': text,
                'upvote': 0,
                'downvote': 0,
                'up_perc': 50,
                'down_perc': 50,
                'from': my_username,
                'to': username,
                'from_id': my_user_id,
                'to_id': user_id,
                'time': r.now().to_iso8601().run(CONNECTION)}).run(CONNECTION)
        SIO.emit('post', data=r.db('roastbook').table('posts').order_by(
            r.desc('time')).limit(100).run(CONNECTION))
        return flask.redirect(flask.url_for('user', username=my_username))
    return user_id


@APP.route("/agb")
def agb():
    """
    flask.Flask Handler for the AGB (Terms of Service)
    """
    return flask.render_template("agb.html")


@APP.route("/impressum")
def impressum():
    """
    flask.Flask Handler for the Impressum (Imprint)
    """
    return flask.render_template("impressum.html")


@APP.route("/datenschutz")
def datenschutz():
    """
    flask.Flask Handler for the Datenschutz (Privacy Policy)
    """
    return flask.render_template("datenschutz.html")


if __name__ == '__main__':
    import eventlet
    eventlet.wsgi.server(eventlet.listen(('', 5000)), APP)
