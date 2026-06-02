from jarvis.core.router import _is_command, _is_question


def test_router_question_heuristics():
    assert _is_question("o que é usb")
    assert _is_question("como configurar docker")
    assert _is_question("quando é o dia das mães")
    assert _is_question("qual o meu ip?")


def test_router_command_heuristics():
    assert _is_command("status do servidor")
    assert _is_command("reiniciar sistema")
    assert _is_command("bloquear site youtube.com")
    assert _is_command("criar lembrete")
