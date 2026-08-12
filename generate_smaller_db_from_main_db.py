import os

import sqlite3


def generate_smaller_db_from_farm_survey_db(new_db_name, new_table_name, column_name, like_value):
    conn = sqlite3.connect(new_db_name)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS farm_survey_paths (filePath, originalName)")

    fs_main_conn = sqlite3.connect("db/farm-survey.db")
    fs_main_cursor = fs_main_conn.cursor()
    fs_main_cursor.execute(
        f"SELECT * FROM farm_survey_paths WHERE {column_name} LIKE ?;", (like_value,)
    )
    fs_results = fs_main_cursor.fetchall()


    cursor.executemany("INSERT INTO farm_survey_paths (filePath, originalName) VALUES (?, ?)", fs_results)
    fs_main_conn.commit()
    fs_main_conn.close()
    conn.commit()
    print("Completed.")
    conn.close()

if __name__ == "__main__":
    new_db_name = ""
    new_table_name = ""
    column_name = "" # filePath or originalName
    like_value = ""
    generate_smaller_db_from_farm_survey_db(f"farm-survey_{new_db_name}.db", new_table_name, column_name, like_value)
