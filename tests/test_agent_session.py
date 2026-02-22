from agent_core.session import SessionManager


def test_session_save_and_load(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:default")
    session.add_message("user", "hello")
    session.add_message("assistant", "hi")
    manager.save(session)

    manager2 = SessionManager(tmp_path)
    loaded = manager2.get_or_create("cli:default")
    history = loaded.get_history()

    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "hello"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "hi"

