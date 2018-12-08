 # -*- coding: utf-8 -*-
from flask import Flask, request, redirect, url_for, render_template, make_response, Markup
import rethinkdb as r
import json
import hashlib
import socketio
from multiprocessing import Process

config = {
    'host':'localhost',
    'user':'admin',
    'password':''
}

with open('config.json') as f:
    config = json.loads(f.read())

sio = socketio.Server()
app = Flask(__name__, static_folder="node_modules")
app.wsgi_app = socketio.Middleware(sio, app.wsgi_app)

connection = r.connect(host=config['host'], user=config['user'], password=config['password'], db='roastbook').repl()
print("host: %s, user: %s" % (config['host'], config['user']), connection.server())
#r.db_create('roastbook').run()
connection.use('roastbook')
#r.table_drop('users').run()
#r.table_create('users').run()
#r.table_drop('posts').run()
#r.table_create('posts').run()
#r.table('users').update({'liked':[]}).run()
#r.table('users').index_create('username').run()

@sio.on('connect')
def connect(sid, environ):
    print("connect ", sid)
    sio.emit('post', data=r.table('posts').order_by(r.desc('time')).limit(100).run(connection))
    sio.emit('top_user', data=r.table('users').order_by(r.desc('balance')).limit(5).pluck(['username', 'balance']).run(connection))
    sio.emit('top_roast', data=r.table('users').order_by(r.asc('balance')).limit(5).pluck(['username', 'balance']).run(connection))
    sio.emit('all_names', data=r.table('users').pluck('username', 'id').coerce_to('array').run(connection))

@sio.on('disconnect')
def disconnect(sid):
    print("disconnect ", sid)

@sio.on('upvote')
def Interactive_upvote(sid, environ=''):
    print("Interactive Upvote", sid, environ)
    vote(1, environ)

@sio.on('downvote')
def interactive_downvote(sid, environ=''):
    print("Interactive Downvote", sid, environ)
    vote(-1, environ)

@app.route("/")
def index():
    return render_template("homepage.html")

@app.route("/login", methods=["POST", "GET"])
def login():
    error = ""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user_data = r.table('users').get_all(username, index='username').coerce_to('array').run(connection)
        if len(user_data) == 0:
            error = "Nutzer nicht gefunden!"
        elif len(user_data) > 1:
            error = "Mehrere Nutzer mit gleichem Namen gefunden, bitte kontaktieren sie den support oder nutzen sie ihre ID als nutzername (z.B. 'id-c73a8f94-a5d6-4234-b88a-a8e5b65ebd88')."
        else:
            data = user_data[0]
            pwd_hash = hashlib.sha256(username + password).hexdigest()
            #print ("ORIG:\t" + str(data['password']))
            #print ("NEW:\t" + str(pwd_hash))
            if data['password'] == pwd_hash:
                resp = make_response(redirect(url_for("user", username=username)))
                resp.set_cookie("user", value=username)
                resp.set_cookie("user_id", value=data['id'])
                return resp
            else:
                error = "Falsches Password."
    else:
        if request.cookies.get("user"):
            resp = make_response(redirect(url_for("index")))
            resp.set_cookie("user", value="")
            resp.set_cookie("user_id", value="")
            return resp
    return render_template("login.html", error=error)

@app.route("/register", methods=["POST", "GET"])
def register():
    error = ""
    if request.method == "POST":
        username = str(Markup.escape(request.form["username"]))
        password = request.form["password"]
        password_repeat = request.form["password_repeat"]
        if r.table('users').filter({'username':username}).count().run(connection) != 0:
            error = "Ein Benutzer mit deinem Benutzernamen existiert bereits, suche dir einen anderen aus."
        elif password != password_repeat:
            error = "Die beiden eingegebenen Passwoerter stimmen nicht ueberein!"
        else:
            pwd_hash = hashlib.sha256(username + password).hexdigest()
            user_id = r.table('users').insert({'username':username, 'password':pwd_hash, 'balance':0, 'liked':[]}).run(connection)['generated_keys'][0]
            print ("New User: %s, id: %s" % (username, user_id))
            resp = make_response(redirect(url_for("user", username=username)))
            resp.set_cookie("user", value=username)
            resp.set_cookie("user_id", value=user_id)
            return resp
    return render_template("register.html", error=error)

@app.route("/users/<username>")
def user(username):
    data = r.table('users').get_all(username, index='username').coerce_to('array').run(connection)
    if len(data) == 1:
        return render_template("user.html", user=data[0], profile=data[0]['id'])
    else:
        return "Diesen Benutzer gibt es nicht!"

@app.route("/edit_post/<id>", methods=["GET", "POST"])
def edit_post(id):
    data = r.table('posts').get(id).run(connection)
    if request.cookies.get("user_id") != data['from_id']:
        return "You are not allowed to do this!\r\n<a href='" + url_for('index') + "'>Back to Homepage</a>"
    if request.method == "POST":
        text = str(Markup.escape(request.form['text']))
        r.table('posts').get(id).update({'text':text}).run(connection)
        return redirect(url_for('user', username=request.cookies.get("user")))
    else:
        return render_template("edit.html", data=data)

@app.route("/upvote")
def upvote():
    user_id = request.cookies.get("user_id")
    if user_id == "":
        return "You are not allowed to do this!\r\n<a href='" + url_for('index') + "'>Back to Homepage</a>"
    id = request.args.get("id")
    source = request.args.get("source", default=url_for("index"))
    vote(1, {'user_id':user_id, 'post_id':id})
    return redirect(source)

@app.route("/downvote")
def downvote():
    user_id = request.cookies.get("user_id")
    if user_id == "":
        return "You are not allowed to do this!\r\n<a href='" + url_for('index') + "'>Back to Homepage</a>"
    id = request.args.get("id")
    source = request.args.get("source", default=url_for("index"))
    vote(-1, {'user_id':user_id, 'post_id':id})
    return redirect(source)


def vote(amount, args):
    user_id = args['user_id']
    id = args['post_id']
    if user_id == '':
        return
    post = r.table('posts').get(id).run(connection)
    post_author = r.table('users').get(post['from_id']).run(connection)
    post_liker = r.table('users').get(user_id).run(connection)
    if post_liker['liked'] != []:
        if id in post_liker['liked']:
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
    if (post['upvote']+post['downvote']) != 0 and post['upvote'] != post['downvote']:
        post['up_perc'] = (float(post['upvote'])/float(post['upvote']+post['downvote']))*100
        post['down_perc'] = (float(post['downvote'])/float(post['upvote']+post['downvote']))*100
    else:
        post['up_perc'] = 50
        post['down_perc'] = 50
    print("Size before: ", post['up_perc'], post['down_perc'])
    min_perc = 15
    if post['up_perc'] < min_perc:
        post['up_perc'] = min_perc
        post['down_perc'] = 100-min_perc
    if post['down_perc'] < min_perc:
        post['down_perc'] = min_perc
        post['up_perc'] = 100-min_perc
    print("Size after: ", post['up_perc'], post['down_perc'])
    post_liker['liked'].append(id)
    #print (str(liked))
    print ("%s liked post %s" % (post_liker['username'], id))
    r.table('users').get(post_author['id']).update({'balance':post_author['balance']}).run(connection)
    r.table('users').get(user_id).update({'liked':post_liker['liked']}).run(connection)
    r.table('posts').get(id).update(post).run(connection)
    sio.emit('post', data=r.table('posts').order_by(r.desc('time')).limit(100).run(connection))
    sio.emit('top_user', data=r.table('users').order_by(r.desc('balance')).limit(5).pluck(['username', 'balance']).run(connection))
    sio.emit('top_roast', data=r.table('users').order_by(r.asc('balance')).limit(5).pluck(['username', 'balance']).run(connection))
    return

@app.route("/newpost", methods=["POST"])
def newpost():
    text = str(Markup.escape(request.form['text']))
    user_id = request.form['username']
    username = r.table('users').get(user_id).pluck('username').run(connection)['username']
    print("Created Post:" + str(username))
    my_username = request.cookies.get("user")
    my_user_id = request.cookies.get("user_id")
    if r.table('users').get(user_id).pluck('id').count().run(connection) == 1:
        r.table('posts').insert({'text':text, 'upvote':0, 'downvote':0, 'up_perc':50, 'down_perc':50, 'from':my_username, 'to':username, 'from_id':my_user_id, 'to_id':user_id, 'time':r.now().to_iso8601().run(connection)}).run(connection)
        sio.emit('post', data=r.table('posts').order_by(r.desc('time')).limit(100).run(connection))
        return redirect(url_for('user', username=my_username))
    return user_id

@app.route("/agb")
def agb():
    return render_template("agb.html")

@app.route("/impressum")
def impressum():
    return render_template("impressum.html")

@app.route("/datenschutz")
def datenschutz():
    return render_template("datenschutz.html")

if __name__ == '__main__':
    import eventlet
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)