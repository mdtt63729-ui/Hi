import yaml
class WorkflowGenerator:
 def android(self,release=True):
  jobs={'build':{'runs-on':'ubuntu-latest','steps':[
   {'uses':'actions/checkout@v4'},
   {'name':'Set up JDK 17','uses':'actions/setup-java@v4','with':{'distribution':'temurin','java-version':'17','cache':'gradle'}},
   {'name':'Make gradlew executable','run':'chmod +x ./gradlew'},
   {'name':'Build','run':'./gradlew assembleRelease' if release else './gradlew assembleDebug'},
   {'name':'Upload APK','uses':'actions/upload-artifact@v4','with':{'name':'release-apk' if release else 'debug-apk','path':'app/build/outputs/apk/**/*.apk'}}]}}
  return yaml.safe_dump({'name':'Android Build','on':{'workflow_dispatch':{}},'jobs':jobs},sort_keys=False)
 def validate(self,text):
  try:
   x=yaml.safe_load(text); return {'valid':isinstance(x,dict),'errors':[] if isinstance(x,dict) else ['Workflow must be a YAML mapping.']}
  except yaml.YAMLError as e: return {'valid':False,'errors':[str(e)]}
