 # -*- coding: utf-8 -*-
from flask import Flask, request, redirect, url_for, render_template, make_response, Markup
import rethinkdb as r
import json
import hashlib

config = {
    'host':'localhost',
    'user':'admin',
    'password':''
}

with open('config.json') as f:
    config = json.loads(f.read())

app = Flask(__name__)
connection = r.connect(host=config['host'], user=config['user'], password=config['password'], db='roastbook').repl()
print(connection.server())
#r.db_create('roastbook').run()
connection.use('roastbook')
#r.table_drop('users').run()
#r.table_create('users').run()
#r.table_drop('posts').run()
#r.table_create('posts').run()
#r.table('users').update({'liked':[]}).run()
#r.table('users').index_create('username').run()

@app.route("/")
def index():
    top_user = r.table('users').order_by(r.desc('balance')).limit(5).pluck(['username', 'balance']).run(connection)
    #print("Top Users: " + str(top_user))
    top_roast = r.table('users').order_by(r.asc('balance')).limit(5).pluck(['username', 'balance']).run(connection)
    #print("Top Roasted: " + str(top_roast))
    top_post = r.table('posts').order_by(r.desc('id')).limit(100).run(connection)
    #print("Top Posts: " + str(top_post))
    for post in top_post:
        if (post['upvote']+post['downvote']) != 0:
            post['up_perc'] = (post['upvote']/(post['upvote']+post['downvote']))*100
            post['down_perc'] = (post['downvote']/(post['upvote']+post['downvote']))*100
        else:
            post['up_perc'] = 50
            post['down_perc'] = 50
        if post['up_perc'] < 10:
            post['up_perc'] = 10
            post['down_perc'] = 90
        if post['down_perc'] < 10:
            post['down_perc'] = 10
            post['up_perc'] = 90
    return render_template("homepage.html", top_user=top_user, top_roast=top_roast, top_post=top_post)

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
        posts = r.table('posts').filter((r.row['from'] == username) | (r.row['to'] == username)).order_by(r.desc('id')).run(connection)
        for post in posts:
            if (post['upvote']+post['downvote']) != 0:
                post['up_perc'] = (post['upvote']/(post['upvote']+post['downvote']))*100
                post['down_perc'] = (post['downvote']/(post['upvote']+post['downvote']))*100
            else:
                post['up_perc'] = 50
                post['down_perc'] = 50
            if post['up_perc'] < 10:
                post['up_perc'] = 10
                post['down_perc'] = 90
            if post['down_perc'] < 10:
                post['down_perc'] = 10
                post['up_perc'] = 90
        all_names = json.dumps(r.table('users').pluck('username', 'id').coerce_to('array').run(connection))
        return render_template("user.html", user=data[0], posts=posts, all_names=all_names)
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
    user = request.cookies.get("user")
    user_id = request.cookies.get("user_id")
    if user == "":
        return "You are not allowed to do this!\r\n<a href='" + url_for('index') + "'>Back to Homepage</a>"
    id = request.args.get("id")
    source = request.args.get("source", default=url_for("index"))
    data = r.table('posts').get(id).pluck('from_id', 'upvote').run(connection)
    username, upvote = data['from_id'], data['upvote']
    balance = r.table('users').get(username).pluck('balance').run(connection)['balance']
    liked = r.table('users').get(user_id).pluck('liked').run(connection)['liked']
    if liked != []:
        if id in liked:
            return redirect(source)
    else:
        liked = []
    liked.append(id)
    #print (str(liked))
    print ("%s liked post %s" % (user, id))
    balance += 1
    upvote += 1
    print ("Balance of %s changed from %d to %d" % (user_id, balance-1, balance))
    r.table('users').get(user_id).update({'balance':balance}).run(connection)
    r.table('users').get_all(user, index='username').update({'liked':liked}).run(connection)
    r.table('posts').get(id).update({'upvote':upvote}).run(connection)
    return redirect(source)

@app.route("/downvote")
def downvote():
    user = request.cookies.get("user")
    user_id = request.cookies.get("user_id")
    if user == "":
        return "You are not allowed to do this!\r\n<a href='" + url_for('index') + "'>Back to Homepage</a>"
    id = request.args.get("id")
    source = request.args.get("source", default=url_for("index"))
    data = r.table('posts').get(id).pluck('from_id', 'downvote').run(connection)
    username, downvote = data['from_id'], data['downvote']
    balance = r.table('users').get(username).pluck('balance').run(connection)['balance']
    liked = r.table('users').get(user_id).pluck('liked').run(connection)['liked']
    if liked != []:
        if id in liked:
            return redirect(source)
    else:
        liked = []
    liked.append(id)
    #print (str(liked))
    print ("%s disliked post %s" % (user, id))
    balance -= 1
    downvote += 1
    print ("Balance of %s changed from %d to %d" % (user_id, balance+1, balance))
    r.table('users').get(user_id).update({'balance':balance}).run(connection)
    r.table('users').get_all(user, index='username').update({'liked':liked}).run(connection)
    r.table('posts').get(id).update({'downvote':downvote}).run(connection)
    return redirect(source)

@app.route("/newpost", methods=["POST"])
def newpost():
    text = str(Markup.escape(request.form['text']))
    user_id = request.form['username']
    username = r.table('users').get(user_id).pluck('username').run(connection)['username']
    print("Created Post:" + str(username))
    my_username = request.cookies.get("user")
    my_user_id = request.cookies.get("user_id")
    if r.table('users').get(user_id).pluck('id').count().run(connection) == 1:
        r.table('posts').insert({'text':text, 'upvote':0, 'downvote':0, 'from':my_username, 'to':username, 'from_id':my_user_id, 'to_id':user_id}).run(connection)
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
    app.run("0.0.0.0", port=8000)
