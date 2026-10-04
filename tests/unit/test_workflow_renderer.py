from app.services.workflow_renderer import render_workflow

def test_steps_use_vertical_timeline_and_real_checkmarks():
    run={'id':1,'run_number':4,'name':'Android Build','status':'completed','conclusion':'success'}
    jobs=[{'name':'build','status':'completed','conclusion':'success','steps':[
        {'name':'Checkout','status':'completed','conclusion':'success'},
        {'name':'Build','status':'completed','conclusion':'success'},
        {'name':'Upload APK','status':'completed','conclusion':'success'}]}]
    text=render_workflow(run,jobs)
    assert '✅ Checkout' in text and '│' in text and '✅ Build' in text
    assert '100%' in text

def test_failed_and_running_step_icons():
    run={'id':2,'name':'Build','status':'in_progress'}
    jobs=[{'name':'build','status':'in_progress','steps':[
        {'name':'Checkout','status':'completed','conclusion':'success'},
        {'name':'Compile','status':'in_progress'},
        {'name':'Upload','status':'queued'}]}]
    text=render_workflow(run,jobs)
    assert '✅ Checkout' in text
    assert '🔄 Compile' in text
    assert '⚪ Upload' in text
    assert '100%' not in text
