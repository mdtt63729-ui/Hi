import time
import bot


def test_progress_bar_is_block_bar():
    assert bot.OperationReporter._bar(0) == '░' * 20
    assert bot.OperationReporter._bar(50) == '█' * 10 + '░' * 10
    assert bot.OperationReporter._bar(99).startswith('█')


def test_final_message_cannot_be_overwritten_by_stale_progress(monkeypatch):
    sent = []

    def fake_edit(token, chat, msg_id, text, keyboard=None):
        sent.append((text, keyboard))
        time.sleep(0.01)

    monkeypatch.setattr(bot, 'tg_edit', fake_edit)
    reporter = bot.OperationReporter('token', 1, 1)
    reporter.advance(99, 'Uploading ZIP…')
    reporter.finish('✅ <b>Project Analysis</b>', [['OK']])
    time.sleep(0.05)

    assert sent[-1] == ('✅ <b>Project Analysis</b>', [['OK']])
