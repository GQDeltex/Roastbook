 # -*- coding: utf-8 -*-
from flask import Flask, request, redirect, url_for, render_template, make_response, Markup
import sqlite3
import json
import hashlib

app = Flask(__name__)
conn = sqlite3.connect("./data.sqlite3")
c = conn.cursor()
#c.execute("DROP TABLE users")
#c.execute("CREATE TABLE users (username VARCHAR(20), password VARCHAR(20), balance INT, level INT, liked TEXT, PRIMARY KEY(username))")
#c.execute("DROP TABLE posts")
#c.execute("CREATE TABLE posts (id INT, content TEXT, upvote INT, downvote INT, user VARCHAR(20), roasted VARCHAR(20), PRIMARY KEY(id))")
#c.execute("UPDATE users SET liked=', '")
#conn.commit()

@app.route("/")
def index():
    top_user_raw = get_data("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 25")
    top_user = []
    for item in top_user_raw:
        top_user.append([(list(item)[0]), str(list(item)[1])])
    #print("Top Users: " + str(top_user))
    top_roast_raw = get_data("SELECT username, balance FROM users ORDER BY balance ASC LIMIT 25")
    top_roast = []
    for item in top_roast_raw:
        top_roast.append([(list(item)[0]), str(list(item)[1])])
    #print("Top Roasted: " + str(top_roast))
    top_post_raw = get_data("SELECT * FROM posts ORDER BY id DESC LIMIT 100")
    top_post = []
    for item in top_post_raw:
        item = list(item)
        if item[3]+item[2] != 0:
            prc1 = float(item[3]/float(item[3]+item[2]))*100
            prc2 = float(item[2]/float(item[3]+item[2]))*100
            if prc1 <= 10:
                prc1 = 10.0
                prc2 = 90.0
            if prc2 <= 10:
                prc2 = 10.0
                prc1 = 90.0
            item.append(prc1)
            item.append(prc2)
        else:
            item.append(50)
            item.append(50)
        top_post.append(list(item))
    #print("Top Posts: " + str(top_post))
    return render_template("homepage.html", top_user=top_user, top_roast=top_roast, top_post=top_post)

@app.route("/login", methods=["POST", "GET"])
def login():
    error = ""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        try:
            data = list(get_data("SELECT * FROM users WHERE username=?", username)[0])
        except Exception as e:
            error = "Dich gibts anscheinen ned oder du bischt zu dumm zum tippen"
            print e
        else:
            pwd_hash = hashlib.sha256(username + password).hexdigest()
            #print ("ORIG:\t" + str(data[1]))
            #print ("NEW:\t" + str(pwd_hash))
            if data[1] == pwd_hash:
                resp = make_response(redirect(url_for("user", username=username)))
                resp.set_cookie("user", value=username)
                return resp
            else:
                error = "Dein Passwort ischt verdraeht"
    else:
        if request.cookies.get("user"):
            resp = make_response(redirect(url_for("index")))
            resp.set_cookie("user", value="")
            return resp
    return render_template("login.html", error=error)

@app.route("/register", methods=["POST", "GET"])
def register():
    error = ""
    if request.method == "POST":
        username = Markup.escape(request.form["username"])
        password = request.form["password"]
        password_repeat = request.form["password_repeat"]
        data = getuser(username)
        if data != None:
            print (data)
            error = "!!!!!!You shall not pass!!!!!!!"
        elif password != password_repeat:
            error = "Dein Passwort isch verdraeht!"
        else:
            pwd_hash = hashlib.sha256(username + password).hexdigest()
            c.execute("INSERT INTO users (username, password, balance, level) VALUES (?, ?, ?, ?)", (username, pwd_hash, 0, 0))
            conn.commit()
            print ("New User: " + username)
            resp = make_response(redirect(url_for("user", username=username)))
            resp.set_cookie("user", value=username)
            return resp
    return render_template("register.html", error=error)

@app.route("/users/<username>")
def user(username):
    data = getuser(username)
    if data != None:
        posts_raw = get_data("SELECT * FROM posts WHERE user=? OR roasted=? ORDER BY id DESC", (username, username))
        posts = []
        for item in posts_raw:
            item = list(item)
            if item[3]+item[2] != 0:
                prc1 = float(item[3]/float(item[3]+item[2]))*100
                prc2 = float(item[2]/float(item[3]+item[2]))*100
                if prc1 <= 10:
                    prc1 = 10.0
                    prc2 = 90.0
                if prc2 <= 10:
                    prc2 = 10.0
                    prc1 = 90.0
                item.append(prc1)
                item.append(prc2)
            else:
                item.append(50)
                item.append(50)
            posts.append(list(item))
        all_names = json.dumps(get_data("SELECT username FROM users"))
        return render_template("user.html", user=data, you=True, posts=posts, all_names=all_names)
    else:
        return "Diesen Benutzer gibt es nicht!"

@app.route("/edit_post/<id>", methods=["GET", "POST"])
def edit_post(id):
    data = get_data("SELECT * FROM posts WHERE id=?", id)[0]
    if request.cookies.get("user") != data[4]:
        return "You are not allowed to do this!\r\n<a href='" + url_for('index') + "'>Back to Homepage</a>"
    if request.method == "POST":
        text = Markup.escape(request.form['text'])
        c.execute("UPDATE posts SET content=? WHERE id=?", (text, id))
        conn.commit()
        return redirect(url_for('user', username=request.cookies.get("user")))
    else:
        return render_template("edit.html", data=data)


@app.route("/upvote")
def upvote():
    if request.cookies.get("user") == "":
        return "You are not allowed to do this!\r\n<a href='" + url_for('index') + "'>Back to Homepage</a>"
    id = int(request.args.get("id"))
    source = request.args.get("source", default=url_for("index"))
    username, upvote, = get_data("SELECT user, upvote FROM posts WHERE id=?", int(id))[0]
    balance,liked, = get_data("SELECT balance,liked FROM users WHERE username=?", str(username))[0]
    if liked != None:
        if liked.find(", " + str(id) + ", ") != -1:
            return redirect(source)
    else:
        liked = ", "
    liked += (str(id) + ", ")
    #print (str(liked))
    print (str(username) + " liked post nr. " + str(id))
    balance += 1
    upvote += 1
    print ("Balance of %s changed from %d to %d" % (username, balance-1, balance))
    c.execute("UPDATE users SET balance=? WHERE username=?", (balance, username))
    c.execute("UPDATE users SET liked=? WHERE username=?", (liked, username))
    c.execute("UPDATE posts SET upvote=? WHERE id=?", (upvote, id))
    conn.commit()
    return redirect(source)

@app.route("/downvote")
def downvote():
    if request.cookies.get("user") == "":
        return "You are not allowed to do this!\r\n<a href='" + url_for('index') + "'>Back to Homepage</a>"
    id = int(request.args.get("id"))
    source = request.args.get("source", default=url_for("index"))
    username, downvote = get_data("SELECT user,downvote FROM posts WHERE id=?", int(id))[0]
    balance,liked, = get_data("SELECT balance,liked FROM users WHERE username=?", str(username))[0]
    if liked != None:
        if liked.find(", " + str(id) + ", ") != -1:
            return redirect(source)
    else:
        liked = ", "
    liked += (str(id) + ", ")
    #print str(liked)
    print (str(username) + " disliked post nr. " + str(id))
    balance -= 1
    downvote += 1
    print ("Balance of %s changed from %d to %d" % (username, balance+1, balance))
    c.execute("UPDATE users SET balance=? WHERE username=?", (balance, username))
    c.execute("UPDATE users SET liked=? WHERE username=?", (liked, username))
    c.execute("UPDATE posts SET downvote=? WHERE id=?", (downvote, id))
    conn.commit()
    return redirect(source)

@app.route("/newpost", methods=["POST"])
def newpost():
    text = Markup.escape(request.form['text'])
    username = request.form['username']
    print("Created Post:" + str(username))
    my_username = request.cookies.get("user")
    if get_data("SELECT username FROM users WHERE username=?", username):
        try:
            id, = get_data("SELECT id FROM posts ORDER BY id DESC LIMIT 1")[0]
        except:
            id = 0
        c.execute("INSERT INTO posts (id, content, upvote, downvote, user, roasted) VALUES (?, ?, 0, 0, ?, ?)", (id+1, text, my_username, username))
        conn.commit()
        return redirect(url_for('user', username=my_username))

@app.route("/agb")
def agb():
    return render_template("agb.html")

@app.route("/impressum")
def impressum():
    return render_template("impressum.html")

@app.route("/datenschutz")
def datenschutz():
    return render_template("datenschutz.html")

def get_data(query, args=""):
    if type(args) != tuple:
        #print ("Args is not tuple")
        #print ("Type: " + str(type(args)))
        #print (str(args))
        if args != "":
            adding = (str(args), )
        else:
            adding = ""
    else:
        adding = args
    #print (str(adding))
    data = c.execute(query, adding)
    return data.fetchall()

def getuser(username):
    #print (str(username))
    query = c.execute("SELECT * FROM users WHERE username=?", (username, ))
    data = query.fetchall()
    #print data
    if data == []:
        return None
    else:
        return list(data[0])

if __name__ == '__main__':
    app.run("0.0.0.0", port=80)
