import json
from neo4j import GraphDatabase  # pip install neo4j https://github.com/neo4j/neo4j-python-driver


def create_nodes_and_relationships(neo4j_driver, sqlite_conn):
    """从 SQLite3 数据创建 Neo4j 节点和关系"""

    def create_user_nodes(tx, sqlite_conn):
        """创建 User 节点"""
        cursor = sqlite_conn.cursor()
        cursor.execute("SELECT user_id, username, email, join_date FROM users")
        users = cursor.fetchall()
        for user in users:
            user_id, username, email, join_date = user
            query = """
                CREATE (p:Paper {
                    oai_id: $user_id,
                    username: $username,
                    email: $email,
                    join_date: $join_date
                })
            """
            tx.run(query, user_id=user_id, username=username, email=email, join_date=join_date)
        print("User 节点创建完成")

    def create_post_nodes(tx, sqlite_conn):
        """创建 Post 节点"""
        cursor = sqlite_conn.cursor()
        cursor.execute("SELECT post_id, title, content, created_at, author_id FROM posts")
        posts = cursor.fetchall()
        for post in posts:
            post_id, title, content, created_at, author_id = post
            query = """
                CREATE (p:Post {
                    post_id: $post_id,
                    title: $title,
                    content: $content,
                    created_at: $created_at
                })
            """
            tx.run(query, post_id=post_id, title=title, content=content, created_at=created_at)
        print("Post 节点创建完成")

    def create_tag_nodes(tx, sqlite_conn):
        """创建 Tag 节点"""
        cursor = sqlite_conn.cursor()
        cursor.execute("SELECT tag_id, tag_name FROM tags")
        tags = cursor.fetchall()
        for tag in tags:
            tag_id, tag_name = tag
            query = """
                CREATE (t:Tag {
                    tag_id: $tag_id,
                    tag_name: $tag_name
                })
            """
            tx.run(query, tag_id=tag_id, tag_name=tag_name)
        print("Tag 节点创建完成")

    def create_authored_by_relationships(tx, sqlite_conn):
        """创建 Post -> User 的 AUTHORED_BY 关系"""
        cursor = sqlite_conn.cursor()
        cursor.execute("SELECT post_id, author_id FROM posts")
        post_authors = cursor.fetchall()
        for post_author in post_authors:
            post_id, author_id = post_author
            query = """
                MATCH (p:Post {post_id: $post_id}), (u:User {user_id: $author_id})
                CREATE (p)-[:AUTHORED_BY]->(u)
            """
            tx.run(query, post_id=post_id, author_id=author_id)
        print("AUTHORED_BY 关系创建完成")

    def create_post_tag_relationships(tx, sqlite_conn):
        """创建 Post -> Tag 的 HAS_TAG 关系 (多对多关系)"""
        cursor = sqlite_conn.cursor()
        cursor.execute("SELECT post_id, tag_id FROM post_tags")
        post_tags_data = cursor.fetchall()
        for pt in post_tags_data:
            post_id, tag_id = pt
            query = """
                MATCH (p:Post {post_id: $post_id}), (t:Tag {tag_id: $tag_id})
                CREATE (p)-[:HAS_TAG]->(t)
            """
            tx.run(query, post_id=post_id, tag_id=tag_id)
        print("HAS_TAG 关系创建完成")

    with neo4j_driver.session() as session:
        session.execute_write(create_user_nodes, sqlite_conn=sqlite_conn)
        session.execute_write(create_post_nodes, sqlite_conn=sqlite_conn)
        session.execute_write(create_tag_nodes, sqlite_conn=sqlite_conn)
        session.execute_write(create_authored_by_relationships, sqlite_conn=sqlite_conn)
        session.execute_write(create_post_tag_relationships, sqlite_conn=sqlite_conn)