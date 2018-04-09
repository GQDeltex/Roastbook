import sqlite3

if __name__ == '__main__':
    conn = sqlite3.connect("data.sqlite3")
    c = conn.cursor()
    saved = False
    while True:
        back = raw_input(">>>")
        if back == "quit" or back == "exit":
            if saved == False:
                print("You haven't saved!")
                back = raw_input("Save? [Y/n]")
                if back == "y" or back == "Y":
                    conn.commit()
            break
        elif back == "save" or back == "write":
            conn.commit()
            saved = True
        elif back == "delete user":
            back = raw_input("username")
            try:
                sql = c.execute("DELETE FROM users WHERE username='%s'" % back)
                print(sql.fetchall())
            except Exception as e:
                print("ERROR: " + str(e))
        else:
            saved = False
            try:
                sql = c.execute(back)
                print(sql.fetchall())
            except Exception as e:
                print("ERROR: " + str(e))
    conn.close()
