import traceback
import ast

from flask import render_template, request, flash, redirect, url_for, jsonify, session, Response
from datetime import timedelta,datetime
from project import csrf
from project import app
from copy import deepcopy

from .modules.servers import *
from .paperdao import *
from .views import *
from .util import *

qresp_config = {}
ftp_dict = {}

class InvalidUsage(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv


@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(days=1)

# Fetches list of qresp servers
@app.route('/')
@app.route('/index')
def index():
    """
    Fetches the homepage
    :return:
    """
    return render_template('index.html')

# Fetches list of qresp servers for the explorer
@app.route('/qrespexplorer')
def qrespexplorer():
    """
    Fetches the explorer homepage
    """
    serverslist = Servers()
    return render_template('qrespexplorer.html', serverslist=serverslist.getServersList())

# Fetches the curator homepage
@app.route('/qrespcurator')
def qrespcurator():
    """
    Fetches the curator homepage
    """
    return render_template('qrespcurator.html')

# Fetches the curator homepage
@csrf.exempt
@app.route('/uploadFile',methods=['POST','GET'])
def uploadFile():
    """
    Upload file text
    """
    uploadJSON = json.loads(request.get_json())
    print(uploadJSON)
    paperform = PaperForm(**uploadJSON)
    session["paper"] = paperform.data
    print(paperform.data)
    session["insertedBy"] = paperform.info.insertedBy.data
    session["serverPath"] = paperform.info.serverPath.data
    session["fileServerPath"] = paperform.info.fileServerPath.data
    session["downloadPath"] = paperform.info.downloadPath.data
    session["gitService"] = paperform.info.gitPath.data
    session["notebookPath"] = paperform.info.notebookPath.data
    session["notebookFile"] = paperform.info.notebookFile.data
    session["doi"] = paperform.info.doi.data
    session["folderAbsolutePath"] = paperform.info.folderAbsolutePath.data
    session["isPublic"] = paperform.info.isPublic.data
    if paperform.info.folderAbsolutePath.data:
        projectName = paperform.info.folderAbsolutePath.data.rsplit("/",1)[1]
        session["ProjectName"] = projectName

    chartList = []
    for eachchartdata in paperform.charts.entries:
        eachchart = eachchartdata.data
        if not eachchart.get("saveas"):
            eachchart["saveas"] = eachchart.get("id")
        chartList.append(eachchart)
    session["charts"] = chartList

    toolList = []
    for eachtooldata in paperform.tools.entries:
        eachtool = eachtooldata.data
        if not eachtool.get("saveas"):
            eachtool["saveas"] = eachtool.get("id")
        toolList.append(eachtool)
    session["tools"] = toolList

    datasetList = []
    for eachdatasetdata in paperform.datasets.entries:
        eachdataset = eachdatasetdata.data
        if not eachdataset.get("saveas"):
            eachdataset["saveas"] = eachdataset.get("id")
        datasetList.append(eachdataset)
    session["datasets"] = datasetList

    scriptList = []
    for eachscriptdata in paperform.scripts.entries:
        eachscript = eachscriptdata.data
        if not eachscript.get("saveas"):
            eachscript["saveas"] = eachscript.get("id")
        scriptList.append(eachscript)
    session["scripts"] = scriptList

    session["heads"] = [form.data for form in paperform.heads.entries]
    session["edges"] = [form.data for form in paperform.workflow.edges.entries]
    session["nodes"] = [form for form in paperform.workflow.nodes.data]
    infoform = InfoForm(**paperform.data)
    infoform.tags.data = ", ".join(paperform.tags.data)
    infoform.collections.data = ", ".join(paperform.collections.data)
    session["info"] = infoform.data
    session["PIs"] = [form.data for form in infoform.PIs.entries]
    session["tags"] = [form for form in paperform.tags.data]
    session["collections"] = [form for form in paperform.collections.data]
    session["workflow"] = paperform.workflow.data
    #workflow
    referenceform = ReferenceForm(**paperform.reference.data)
    session["reference"] = referenceform.data

    print("s>>",session.get("tags"),session.get("collections"),session.get("edges"),session.get("heads"),session.get("nodes"))
    print("c>>",session.get("charts"))
    return jsonify(out="done")


@app.route('/details', methods=['POST', 'GET'])
def details():
    """ This method helps in storing the details of the curator.
    :return:
    """
    form = DetailsForm(request.form)
    if request.method == 'POST' and form.validate():
        session["insertedBy"] = form.data
        return redirect(url_for('server'))
    elif session.get("insertedBy"):
        detailsForm = session.get("insertedBy")
        form = DetailsForm(**detailsForm)
    return render_template('details.html', form=form)

@csrf.exempt
@app.route('/server', methods=['POST', 'GET'])
def server():
    """ This method helps in connecting to the server.
    :return:
    """
    form = ServerForm(request.form)
    if request.method == 'POST' and form.validate():
        try:
            sftp = ConnectToServer(form.serverName.data,form.username.data,form.password.data,form.isDUOAuth.data,"1")
            session["sftpclient"] = form.username.data
            ftp_dict[form.username.data] = sftp.getSftp()
            return redirect(url_for('project'))
        except Exception as e:
            flash("Could not connect to server. Plase try again!"+str(e))
            render_template('server.html', form=form)
    return render_template('server.html', form=form)

# @csrf.exempt
# @app.route('/project', methods=['POST', 'GET'])
# def project():
#     """ This method helps in connecting to the server.
#     :return: template project.html
#     """
#     form = ProjectForm(request.form)
#     if session.get("project"):
#         session["project"] = form.data
#     elif session.get("fileServerPath"):
#         form.fileServerPath = session.get("fileServerPath")
#     return render_template('project.html', form=form)

@csrf.exempt
@app.route('/project', methods=['POST', 'GET'])
def project():
    """ This method helps in connecting to the server.
    :return: template project.html
    """
    form = ProjectForm(request.form)
    # absPath = ""
    if request.method == 'GET':
        if session.get("folderAbsolutePath"):
            form.folderAbsolutePath.data = session.get("folderAbsolutePath")
        else:
            form.folderAbsolutePath.data = "."
        print("GETp>>",form.data)
        return render_template('project.html', form=form)

@csrf.exempt
@app.route('/setproject', methods=['POST', 'GET'])
def setproject():
    if request.method == 'POST':
        pathDetails = request.get_json()
        absPath = pathDetails['folderAbsolutePath']
        ftpclient = session.get("sftpclient")
        ftp = ftp_dict[ftpclient]
        print("absPath",absPath.rsplit("/", 1)[0])
        dtree = Dtree(ftp, absPath.rsplit("/", 1)[0], session)
        dtree.openFileToReadConfig("qresp.ini")
        services = dtree.fetchServices()
        isConfig = dtree.checkIsConfigFile()
        print("isConfig",isConfig)
        session["folderAbsolutePath"] = absPath
        session["ProjectName"] = absPath.rsplit("/",1)[1]
        return jsonify(folderAbsolutePath=absPath,isConfigFile=isConfig,services=services)

@csrf.exempt
@app.route('/getTreeInfo', methods=['POST', 'GET'])
def getTreeInfo():
    """
    Renders the Tree containing Project Information which is 'SSH'ed with the remote directory.
    :return:
    """
    pathDetails = request.get_json()
    listObjects = []
    services = []
    ftpclient = session.get("sftpclient")
    ftp = ftp_dict[ftpclient]
    if 'folderAbsolutePath' in pathDetails:
        content_path = pathDetails['folderAbsolutePath']
    else:
        content_path = session.get("folderAbsolutePath")
    try:
        dtree = Dtree(ftp,content_path,session)
        listObjects = dtree.fetchForTree()
        services = dtree.fetchServices()
    except Exception as e:
        print(e)
    return jsonify({'listObjects': listObjects, 'services': services})

@app.route('/curate', methods=['POST', 'GET'])
def curate():
    """ This method helps in connecting to the server.
    :return:
    """
    print("inside c>>",session.get("folderAbsolutePath"))
    infoform = InfoForm(request.form)
    chartform = ChartForm(request.form)
    toolform = ToolForm(request.form)
    datasetform = DatasetForm(request.form)
    scriptform = ScriptForm(request.form)
    referenceform = ReferenceForm(request.form)
    documentationform = DocumentationForm(request.form)
    chartlist = []
    toollist = []
    datasetlist = []
    scriptlist = []
    projectName = ""
    if session.get("info"):
        sessionInfoForm = session.get("info")
        infoform = InfoForm(**sessionInfoForm)
    if session.get("charts",[]):
        chartlist = deepcopy(session.get("charts",[]))
    if session.get("tools",[]):
        toollist = deepcopy(session.get("tools",[]))
        print("t1",toollist)
    if session.get("datasets",[]):
        datasetlist = deepcopy(session.get("datasets",[]))
    if session.get("scripts",[]):
        scriptlist = deepcopy(session.get("scripts",[]))
    if session.get("folderAbsolutePath"):
        projectName = session.get("folderAbsolutePath").rsplit("/", 1)[1]
    if session.get("reference"):
        referenceForm = session.get("reference")
        referenceform = ReferenceForm(**referenceForm)
    return render_template('curate.html',infoform=infoform,chartlistform=chartlist,chartform=chartform,
                           toollistform=toollist,toolform=toolform,datalistform=datasetlist,datasetform=datasetform,
                           scriptlistform=scriptlist,scriptform=scriptform,referenceform=referenceform,projName=projectName,documentationform=documentationform)

@csrf.exempt
@app.route('/info', methods=['POST', 'GET'])
def info():
    """ This method helps in connecting to the server.
    :return:
    """
    infoform = InfoForm(request.form)
    if request.method == 'POST' and infoform.validate():
        session["info"] = infoform.data
        session["PIs"] = [form.data for form in infoform.PIs.entries]
        session["tags"] = infoform.tags.data.split(",")
        session["collections"] = infoform.collections.data.split(",")
        session["notebookFile"] = infoform.mainnotebookfile.data
        msg = "Info Saved"
        return jsonify(data=msg)
    return jsonify(data=infoform.errors)

@csrf.exempt
@app.route('/charts', methods=['POST', 'GET'])
def charts():
    """ This method helps in connecting to the server.
    :return:
    """
    chartform = ChartForm(request.form)
    if request.method == 'POST' and chartform.validate():
        chartList = deepcopy(session.get("charts", []))
        print("len>>", len(chartList))
        print(chartList)
        if len(chartList) <  1:
            chartList.append(chartform.data)
            session["charts"] = deepcopy(chartList)
        else:
            idList = [eachchart['saveas'] if eachchart['saveas'] else eachchart['id'] for eachchart in chartList]
            id = chartform.id.data
            saveas = chartform.saveas.data
            if id not in idList and saveas not in idList:
                chartList.append(chartform.data)
                session["charts"] = deepcopy(chartList)
            else:
                chartList = [item for item in chartList if item['saveas'] not in chartform.saveas.data]
                chartList.append(chartform.data)
                session["charts"] = deepcopy(chartList)
        return jsonify(chartList = chartList)
    return jsonify(data=chartform.errors)

@csrf.exempt
@app.route('/tools', methods=['POST', 'GET'])
def tools():
    """ This method helps in populating tools section in the curator.
    :return:
    """
    toolform = ToolForm(request.form)
    if request.method == 'POST' and toolform.validate():
        toolList = deepcopy(session.get("tools", []))
        print(toolList)
        if len(toolList) <  1:
            toolList.append(toolform.data)
            session["tools"] = deepcopy(toolList)
        else:
            idList = [eachtool['saveas'] if eachtool['saveas'] else eachtool['id'] for eachtool in toolList]
            id = toolform.id.data
            saveas = toolform.saveas.data
            if id not in idList and saveas not in idList:
                toolList.append(toolform.data)
                session["tools"] = deepcopy(toolList)
            else:
                toolList = [item for item in toolList if item['saveas'] not in toolform.saveas.data]
                toolList.append(toolform.data)
                session["tools"] = deepcopy(toolList)
        return jsonify(toolList = toolList)
    return jsonify(errors=toolform.errors)

@csrf.exempt
@app.route('/datasets', methods=['POST', 'GET'])
def datasets():
    """ This method helps in populating datasets section in the curator.
    :return:
    """
    datasetform = DatasetForm(request.form)
    if request.method == 'POST' and datasetform.validate():
        datasetList = deepcopy(session.get("datasets", []))
        print(datasetList)
        if len(datasetList) <  1:
            datasetList.append(datasetform.data)
            session["datasets"] = deepcopy(datasetList)
        else:
            idList = [eachdataset['saveas'] if eachdataset['saveas'] else eachdataset['id'] for eachdataset in datasetList]
            id = datasetform.id.data
            saveas = datasetform.saveas.data
            if id not in idList and saveas not in idList:
                datasetList.append(datasetform.data)
                session["datasets"] = deepcopy(datasetList)
            else:
                datasetList = [item for item in datasetList if item['saveas'] not in datasetform.saveas.data]
                datasetList.append(datasetform.data)
                session["datasets"] = deepcopy(datasetList)
        return jsonify(datasetList = datasetList)
    return jsonify(data=datasetform.errors)

@csrf.exempt
@app.route('/scripts', methods=['POST', 'GET'])
def scripts():
    """ This method helps in populating scripts section in the curator.
    :return:
    """
    scriptform = ScriptForm(request.form)
    if request.method == 'POST' and scriptform.validate():
        scriptList = deepcopy(session.get("scripts", []))
        print(scriptList)
        if len(scriptList) <  1:
            scriptList.append(scriptform.data)
            session["scripts"] = deepcopy(scriptList)
        else:
            idList = [eachscript['saveas'] if eachscript['saveas'] else eachscript['id'] for eachscript in scriptList]
            id = scriptform.id.data
            saveas = scriptform.saveas.data
            if id not in idList and saveas not in idList:
                scriptList.append(scriptform.data)
                session["scripts"] = deepcopy(scriptList)
            else:
                scriptList = [item for item in scriptList if item['saveas'] not in scriptform.saveas.data]
                scriptList.append(scriptform.data)
                session["scripts"] = deepcopy(scriptList)
        return jsonify(scriptList = scriptList)
    return jsonify(data=scriptform.errors)

@csrf.exempt
@app.route('/reference', methods=['POST', 'GET'])
def reference():
    """ This method helps in connecting to the server.
    :return:
    """
    referenceform = ReferenceForm(request.form)
    if request.method == 'POST' and referenceform.validate():
        session["reference"] = referenceform.data
        msg = "Reference Saved"
        return jsonify(data=msg)
    return jsonify(data=referenceform.errors)

@csrf.exempt
@app.route('/fetchReferenceDOI', methods=['POST', 'GET'])
def fetchReferenceDOI():
    """ This method helps in connecting to the server.
    :return:
    """
    reqDOI = request.get_json()
    print("r",reqDOI)
    try:
        fetchDOI = FetchDOI(reqDOI["doi"])
        refdata = fetchDOI.fetchFromDOI()
        print("here",refdata.data)
    except Exception as e:
        print(e)
        return jsonify(errors="Recheck your DOI")
    return jsonify(fetchDOI=refdata.data)

@csrf.exempt
@app.route('/documentation', methods=['POST', 'GET'])
def documentation():
    """ This method helps in adding documentation to the paper.
    :return:
    """
    docform = DocumentationForm(request.form)
    if request.method == 'POST' and docform.validate():
        session["documentation"] = docform.data
        msg = "Documentation Saved"
        return jsonify(data=msg)
    return jsonify(data=docform.errors)

@csrf.exempt
@app.route('/workflow', methods=['POST', 'GET'])
def workflow():
    """Collects and Returns values needed for the Workflow section.
	:return: Information of the various nodes and edges - Dictionary
	"""
    generateIDs = GenerateIDs(session)
    if request.method == 'GET':
        return render_template('workflow.html')
    nodesList = []
    workflowsave = request.json
    workflow = WorkflowCreator()
    for chart in session.get("charts",[]):
        try:
            fileServerPath = session.get("fileServerPath","")
            projectName = session.get("ProjectName","")
            if projectName not in fileServerPath:
                img = '<img src="' + fileServerPath  + "/" + projectName+"/"+chart["imageFile"] + '" width="250px;" height="250px;"/>'
            else:
                img = '<img src="' + fileServerPath  +"/"+chart["imageFile"] + '" width="250px;" height="250px;"/>'
            print("img",img)
            caption = "<b> Image: </b>" + img
        except Exception as e:
            caption = ""
        nodesList.append(chart["saveas"])
        workflow.addChart(chart["saveas"], caption)
    for tool in session.get("tools",[]):
        pack = ""
        try:
            pack = "<b> Package Name: </b>" + tool["packageName"]
        except:
            try:
                pack = "<b> Facility Name: </b>" + tool["facilityName"] + " <br/> <b>Measurement: </b>" + tool["measurement"]
            except:
                pack = ""
        nodesList.append(tool["saveas"])
        workflow.addTool(tool["saveas"], pack)
    for dataset in session.get("datasets",[]):
        readme = ""
        try:
            readme = "<b> ReadMe: </b>" + dataset["readme"]
        except:
            readme = ""
        nodesList.append(dataset["saveas"])
        workflow.addDataset(dataset["saveas"], readme)
    for script in session.get("scripts",[]):
        readme = ""
        try:
            readme = "<b> ReadMe: </b>" + script["readme"]
        except:
            readme = ""
        if not script["saveas"]:
            script["saveas"] = script["id"]
        nodesList.append(script["saveas"])
        workflow.addScript(script["saveas"], readme)
    for head in session.get("heads",[]):
        readme = ""
        try:
            readme = head["readme"]
        except:
            readme = ""
        #saveas = head.split("*")
        try:
            nodesList.append(head["id"])
            workflow.addHead(head["id"], readme, head["URLs"])
        except:
            nodesList.append(head["id"])
            workflow.addHead(head["id"], readme)

    for edge in session.get("edges",[]):
        workflow.addEdge(edge)
    try:
        listConn = str(workflowsave[0])
        edgeList = []
        for edge in workflowsave[0]:
            workflow.addEdge(edge)
            edgeList.append(edge)
        session["edges"] = edgeList
        print("edgeList>>",edgeList)
    except Exception as e:
        print(e)
        listConn = ""
    try:
        heads = HeadForm(request.form)
        headInfo = str(workflowsave[1])
        headList = []
        for head in ast.literal_eval(headInfo):
            hinfo = head.split("*")
            nodesList.append(hinfo["id"])
            try:
                if hinfo[1] and not hinfo[1].isspace():
                    heads.readme.data = str(hinfo[1])
            except Exception as e:
                print(e)
                print("No readme")
            try:
                if hinfo[2] and not hinfo[2].isspace():
                        heads.URLs.data = str(info).strip()
            except Exception as e:
                print(e)
                print("No Url")
            headList.append(heads.data)
        session["heads"] = headList
        print("headlist>>",headList)
        nodesList = list(set(nodesList))
        workflowinfo = WorkflowForm(edges = edgeList,nodes=nodesList)
        session["workflow"] = workflowinfo.data
    except:
        headInfo = ""
    return jsonify({'workflow': workflow.__dict__})

# Fetches list of qresp servers for the explorer
@csrf.exempt
@app.route('/publish', methods=['POST', 'GET'])
def publish():
    """
    Published the created metadata
    """
    form = PublishForm(request.form)
    if request.method == 'GET':
        serverslist = Servers()
        form.server.choices = [(qrespserver['qresp_server_url'],qrespserver['qresp_server_url']) for qrespserver in serverslist.getServersList()]
        return render_template('publish.html', form=form)


@csrf.exempt
@app.route('/download', methods=['POST', 'GET'])
def download():
    """
    Downloads the created metadata
    :return:
    """
    details = session.get("details")
    PIs = session.get("PIs")
    charts = session.get("charts")
    collections = session.get("collections")
    datasets = session.get("datasets")
    info = session.get("info")
    reference = session.get("reference")
    scripts = session.get("scripts")
    tools = session.get("tools")
    tags = session.get("tags")
    versions = session.get("versions")
    workflow = session.get("workflow")
    heads = session.get("heads")
    projectName = session.get("ProjectName","unknown")
    pubdate = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    projectForm = ProjectForm(downloadPath = session.get("downloadPath"),fileServerPath = session.get("fileServerPath"),notebookPath = session.get("notebookPath"),
                              folderAbsolutePath = session.get("folderAbsolutePath"),ProjectName = session.get("ProjectName"),gitPath = session.get("gitPath"),
                              insertedBy = session.get("insertedBy"),isPublic = session.get("isPublic"),timeStamp = pubdate,
                              serverPath = session.get("serverPath"),notebookFile = session.get("notebookFile"),doi = session.get("doi"))
    print("here>>Downloads>>",details,PIs,charts,collections,datasets,projectForm.data,info,reference,scripts,tools,tags,versions,workflow,heads)

    paperform = PaperForm(PIs = PIs, charts = charts, collections=collections, datasets = datasets, info = projectForm.data,
                          reference = reference, scripts =scripts, tools = tools,
                          tags = tags,versions =versions, workflow=workflow,heads=heads,schema='http://paperstack.uchicago.edu/v1_0.json',version=1)
    print(paperform.data)
    if not os.path.exists(projectName):
        os.makedirs(projectName)
    with open(projectName+"/"+"data.json", "w") as outfile:
        json.dump(paperform.data, outfile, default=lambda o: o.__dict__, separators=(',', ':'), sort_keys=True, indent=3)
    return jsonify(paper=paperform.data)


@csrf.exempt
@app.route('/acknowledgement', methods=['POST', 'GET'])
def acknowledgement():
    """
    Downloads the created metadata
    :return:
    """
    return render_template('acknowledgement.html')

########################################EXPLORER#############################################################################


@csrf.exempt
@app.route('/verifyPasscode',methods=['POST','GET'])
def verifypasscode():
    """ This method verifies with input passcode of flask connection.
    :return:
    """
    form = PassCodeForm(request.form)
    confirmpasscode = app.config['passkey']
    if request.method == 'POST' and form.validate():
        print("here>",confirmpasscode)
        print("here1>",form.passcode.data)
        if confirmpasscode == form.passcode.data:
            return jsonify(msg="success")
    else:
        print("why")
    return jsonify(msg="failed")

# Fetches list of qresp admin
@csrf.exempt
@app.route('/admin', methods=['POST', 'GET'])
def admin():
    """ This method helps in connecting to the mongo database.
    :return:
    """
    form = AdminForm(request.form)
    verifyform = PassCodeForm(request.form)
    if request.method == 'POST' and form.validate():
        flash('Connected')
        try:
            dbAdmin = MongoDBConnection(hostname=form.hostname.data, port=int(form.port.data),
                                        username=form.username.data, password=form.password.data,
                                        dbname=form.dbname.data, collection=form.collection.data, isssl=form.isSSL.data)
            return redirect(url_for('config'))
        except ConnectionError as e:
            raise InvalidUsage('Could not connect to server, \n ' + str(e), status_code=410)

    # ##### To be removed ###########
    # form.hostname.data = "paperstack.uchicago.edu"
    # form.port.data = "27017"
    # form.username.data = "qresp_user_explorer"
    # form.password.data = "qresp_pwd"
    # form.dbname.data = "explorer"
    # form.collection.data = "paper"
    return render_template('admin.html', form=form,verifyform =verifyform )

# Fetches list of qresp admin
@csrf.exempt
@app.route('/config', methods=['POST', 'GET'])
def config():
    """ This method helps in connecting to the mongo database.
    :return:
    """
    form = ConfigForm(request.form)
    app.config['qresp_config']['fileServerPath'] = 'https://notebook.rcc.uchicago.edu/files'
    app.config['qresp_config']['downloadPath'] = 'https://www.globus.org/app/transfer?origin_id=72277ed4-1ad3-11e7-bbe1-22000b9a448b&origin_path='
    verifyform = PassCodeForm(request.form)

    return render_template('config.html', form=form,verifyform =verifyform)


# Fetches search options after selecting server
@csrf.exempt
@app.route('/search', methods=['POST', 'GET'])
def search():
    """  This method helps in filtering paper content
    :return: template: search.html
    """
    try:
        db = MongoDBConnection(hostname="paperstack.uchicago.edu", port=int("27017"), username="qresp_user_explorer",
                               password="qresp_pwd", dbname="explorer", collection="paper", isssl="No")
        dao = PaperDAO()
        return render_template('search.html',
                               collectionlist=dao.getCollectionList(), authorslist=dao.getAuthorList(),
                               publicationlist=dao.getPublicationList(), allPapersSize=len(dao.getAllSearchObjects()))
    except Exception as e:
        print(e)
        print(traceback.format_exc())
        flash('Error in search. ' + str(e))
        return render_template('search.html')


# Fetches search word options after selecting server
@csrf.exempt
@app.route('/searchWord', methods=['POST', 'GET'])
def searchWord():
    """  This method helps in filtering paper content
    :return: object: allpaperlist
    """
    try:
        dao = PaperDAO()
        searchWord = request.args.get('searchWord', type=str)
        paperTitle = request.args.get('paperTitle', type=str)
        doi = request.args.get('doi', type=str)
        tags = request.args.get('tags', type=str)
        collectionList = json.loads(request.args.get('collectionList'))
        authorsList = json.loads(request.args.get('authorsList'))
        publicationList = json.loads(request.args.get('publicationList'))
        allpaperslist = dao.getAllFilteredSearchObjects(searchWord, paperTitle, doi, tags, collectionList, authorsList,
                                                        publicationList)
        return jsonify(allpaperslist=allpaperslist)
    except Exception as e:
        print(e)
        print(traceback.format_exc())
        flash('Error in search. ' + str(e))


# Fetches details of chart based on user click
@csrf.exempt
@app.route('/paperdetails/<paperid>', methods=['POST', 'GET'])
def paperdetails(paperid):
    """  This method helps in fetching papers details content
    :return: template: paperdetails.html
    """
    try:
        dao = PaperDAO()
        paperdetail = dao.getPaperDetails(paperid)
        workflowdetail = dao.getWorkflowDetails(paperid)
        return render_template('paperdetails.html', paperdetail=paperdetail, workflowdetail=workflowdetail)
    except Exception as e:
        print(e)
        flash('Error in paperdetails. ' + str(e))


# Fetches workflow of chart based on user click
@csrf.exempt
@app.route('/charworkflow', methods=['POST', 'GET'])
def charworkflow():
    """  This method helps in fetching chart workflow content
    :return: object: chartworkflow
    """
    try:
        dao = PaperDAO()
        paperid = request.args.get('paperid', 0, type=str)
        paperid = str(paperid).strip()
        chartid = request.args.get('chartid', 0, type=str)
        chartid = str(chartid).strip()
        chartworkflowdetail = dao.getWorkflowForChartDetails(paperid, chartid)
        return jsonify(chartworkflowdetail=chartworkflowdetail)
    except Exception as e:
        print(e)
        flash('Error in paperdetails. ' + str(e))