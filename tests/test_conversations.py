from app.conversations import add_message, init_db


def test_conversation_crud_is_user_scoped(client):
    init_db()
    created = client.post("/conversations", json={"title": "Supply chain"}).json()
    conversation_id = created["id"]
    assert created["title"] == "Supply chain"

    listed = client.get("/conversations").json()["conversations"]
    assert any(item["id"] == conversation_id for item in listed)

    renamed = client.patch(
        f"/conversations/{conversation_id}", json={"title": "Risk review"}
    ).json()
    assert renamed["title"] == "Risk review"

    detail = client.get(f"/conversations/{conversation_id}").json()
    assert detail["messages"] == []

    deleted = client.delete(f"/conversations/{conversation_id}")
    assert deleted.status_code == 200
    assert client.get(f"/conversations/{conversation_id}").status_code == 404


def test_conversations_do_not_leak_across_workspaces(client):
    init_db()
    first = client.post(
        "/conversations",
        json={"title": "Workspace A"},
        headers={"X-Workspace-Id": "workspaceA123"},
    ).json()
    other_list = client.get(
        "/conversations",
        headers={"X-Workspace-Id": "workspaceB123"},
    ).json()["conversations"]
    assert first["id"] not in {item["id"] for item in other_list}


def test_messages_stay_isolated_between_conversations(client):
    init_db()
    first = client.post("/conversations", json={"title": "Alpha"}).json()
    second = client.post("/conversations", json={"title": "Beta"}).json()
    add_message("ws:anonymous", first["id"], "user", "Question A")
    add_message("ws:anonymous", first["id"], "assistant", "Answer A")
    add_message("ws:anonymous", second["id"], "user", "Question B")
    add_message("ws:anonymous", second["id"], "assistant", "Answer B")

    first_messages = client.get(f"/conversations/{first['id']}").json()["messages"]
    second_messages = client.get(f"/conversations/{second['id']}").json()["messages"]
    assert [item["content"] for item in first_messages] == ["Question A", "Answer A"]
    assert [item["content"] for item in second_messages] == ["Question B", "Answer B"]


def test_editing_a_user_message_removes_later_turns(client):
    init_db()
    conversation = client.post("/conversations", json={"title": "Edit"}).json()
    user = add_message("ws:anonymous", conversation["id"], "user", "Original question")
    add_message("ws:anonymous", conversation["id"], "assistant", "Original answer")
    updated = client.patch(
        f"/conversations/{conversation['id']}/messages/{user['id']}",
        json={"content": "Edited question"},
    ).json()
    assert updated["content"] == "Edited question"
    remaining = client.get(f"/conversations/{conversation['id']}").json()["messages"]
    assert len(remaining) == 1
    assert remaining[0]["content"] == "Edited question"
