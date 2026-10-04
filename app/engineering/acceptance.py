ACCEPTANCE=[
 'github_connect','repository_list','repository_select','file_browse','branch_manage','zip_upload','repository_update_sync','commit','workflow_create','workflow_run','live_job_step_progress','build_logs','error_txt','ai_error_analysis','authorized_ai_code_fix','rebuild','artifact_delivery','pr_manage','issue_manage','release_manage','natural_language_commands','openrouter_config','gemini_config','ollama_config','provider_fallback','telegram_formatting','danger_confirmation','single_message_monitoring','restart_recovery','no_fabricated_results']
def evaluate(features):
 return {name:bool(features.get(name,False)) for name in ACCEPTANCE}
def complete(features): return all(evaluate(features).values())
