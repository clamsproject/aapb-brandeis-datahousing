import sqlite3

connection = sqlite3.connect('database.db')


with open('schema.sql') as f:
    connection.executescript(f.read())

cur = connection.cursor()

cur.execute("INSERT INTO map VALUES ('cpb-aacip-507-zw18k75z4h', 'text', 'NewsHour/cpb-aacip-507-zw18k75z4h.vtt')")

cur.execute("INSERT INTO map VALUES ('cpb-aacip-507-zw18k75z4h', 'video', 'NewsHour/cpb-aacip-507-zw18k75z4h.mp4')")

connection.commit()
connection.close()