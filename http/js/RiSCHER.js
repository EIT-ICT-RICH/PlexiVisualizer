
//global variables
var dotdata = "digraph testgraph{{node[shape=none,fontsize=23]\"Welcome to Liviz.js!\"}{node[shape=none]\"Interactive GraphViz on your browser\"}{edge[color=transparent]\"Welcome to Liviz.js!\" ->\"Interactive GraphViz on your browser\"}A -> B -> C -> D -> E;	B -> D;{node[shape=box];1 -> 2 -> 3;}E -> 1;2 -> C;{rank=same; 1; A;}{rank=same; 3; D;}}";
var identity = "testserver1";
var state = 0; //-2: receiving boot info, -1: logging in 0: open for new graphs 1: busy with receiving graphparts, 2: requested history, 3: receiving history, 4: receiving matrix info
var menudata = "";
var matrixdata = "";
var matrix = {};
var schedulers  = [];
var menu = {
  "aaaa::215:8d00:57:6466" : [],
  "aaaa::215:8d00:57:1234" : []
};
var frames = {};

window.selectedCell = null;
function ClickCell(obj){
  if(window.selectedCell != null)
  {
    window.selectedCell.style.border="";
  }
  obj.style.border="0.5px solid red";
  window.selectedCell = obj;
  console.log(obj.id);
  var infos = obj.id.split('.');
  $("#matrixinfo").html(window.matrix[infos[0]][infos[1]][infos[2]][1]);
}

//function that is called when the user clicks login
window.bootup = function bootup()
{
  //build json login package
  var loginpacket = {
    "name" 				: $("#user_name").val(),
    "password" 		: $("#user_password").val(),
    "schedulers"	: $("#user_schedulers").val()
  };

  window.schedulers = $("#user_schedulers").val().split(";");
  var form = $(".login-form");
  //fade out and remove the login form
  form.css({
      opacity: 0,
      "-webkit-transform": "scale(1)",
      "transform": "scale(1)",
      "-webkit-transition": ".5s",
      "transition": ".5s"
  });
  $('#login').delay(500).fadeOut();

  // console.log("ws://" + $("#user_serverip").val() + ":600");
  //set the correct state and connect to the server
  window.state = -1;
  window.connect("ws://" + $("#user_serverip").val() + ":600", JSON.stringify(loginpacket));
}

//the function that sets up the connection
window.connect = function connect(host, loginpackage){

try{
  window.socket = new WebSocket(host);
  //when the sockets opens send the loginpackage
  socket.onopen = function(){
    console.log('Socket Status: '+socket.readyState+' (open)');
    socket.send(loginpackage);
  }

//handling incomming messages
  socket.onmessage = function(msg){
    //parse incomming message depending on current state of the system
    switch(window.state)
    {
      case -2: //receiving boot info
        window.frameinfo = JSON.parse(msg.data);
        //build html for tabcontrol for matrix
        var html = "<div class=\"tabcontrol2\" data-role=\"tabControl\"><ul class=\"tabs\">";
        // for(var i = 0; i < frames.length; i++)
        for(frame in window.frameinfo)
        {
          html += "<li><a href=\"#" + frame + "\">" + frame + "</a></li>";
        }
        html += "</ul><div class=\"frames\">";
        // for(var i = 0; i < frames.length; i++)
        for(frame in window.frameinfo)
        {
          html += "<div class=\"frame matrix\" id=\"" + frame + "\"></div>";
        }
        html += "</div></div>";
        $("#schedulestuff").html(html);
        //init the matrices
        // for(var i = 0; i < frames.length; i++)
        for(frame in window.frameinfo)
        {
          window.matrix[frame] = [];
          //init the matrix
          for(var y = 0; y < 16; y++)
          {
            window.matrix[frame].push([]);
            for(var x = 0; x < window.frameinfo[frame]; x++)
            {
              window.matrix[frame][y].push([0,"Not Used"]);
            }
          }

        }
        console.log(window.matrix);
        window.state = 0;
        //unhide the div
        $("#app").removeClass("hidden");
        //and activate the graphviz javascript renderer
        w_launch();
        RequestUpdateMenu();
        for(frame in window.frameinfo)
        {
          window.RenderMatrix(frame);
        }
        break;
      case -1: //logging in
      //check the status and give feedback to the user
        if(msg.data == "OK")
        {
            setTimeout(function(){
                $.Notify({type: 'success', caption: 'Success', content: "Login succesfull, booting app"});
            }, 2000);
            //change state to bootstrap
            window.state = -2;
            console.log("first step");
        }
        else if(msg.data == "WRONG")
        {
            setTimeout(function(){
              $.Notify({type: 'alert', caption: 'Alert', content: "Server refused login!"});
            }, 2000);
            //close the socket as login has failed
            socket.close()
        }
        break;
      case 0: //open for new graphs
        //implemented statemachine because of splitting of dot files. see python code for more info
        if(msg.data == "$STARTGRAPH")
        {
          console.debug("started receiving graph");
          window.dotdata = "";
          window.state = 1;
        }
        else if(msg.data == "$STARTMATRIXUPDATE")
        {
          console.debug("receiving matrix update");
          window.matrixdata = "";
          window.state = 4;
        }
        else
        {
          console.debug("received graph in one packet");
          window.dotdata = msg.data;
          window.ParsePacket();
        }
        break;
      case 1: //busy with receiving graphparts
        if(msg.data == "$ENDGRAPH")
        {
          console.debug("ended receiving graph");
          window.state = 0;
          window.ParsePacket();
        }
        else
        {
          window.dotdata = window.dotdata + msg.data;
        }
        break;
      case 2: //requested history
      //again statemachine
        if(msg.data == "$STARTGRAPH")
        {
          console.debug("started receiving stuff");
          window.menudata = "";
          window.state = 3;
        }
        else
        {
          console.debug("received stuff in one packet");
          window.menudata = msg.data;
          window.state = 0;
          window.ParseMenu();
        }
        break;
      case 3: //receiving history
        if(msg.data == "$ENDGRAPH")
        {
          console.debug("ended receiving stuff");
          window.state = 0;
          window.ParseMenu();
        }
        else
        {
          window.menudata = window.menudata + msg.data;
        }
        break;
      case 4: //receiving matrix info
      //state machine implementation
        if(msg.data == "$ENDMATRIXUPDATE")
        {
          console.debug("ended receiving matrix info");
          window.state = 0;
          window.UpdateMatrix();
        }
        else
        {
          window.matrixdata += msg.data;
        }
        break;
    }
    //log the message
    console.log('Received: ' + msg.data);
  }

  //when the sockets closes display red banner to the user
  socket.onclose = function(){
    console.log('Socket Status: '+socket.readyState+' (Closed)');
    setTimeout(function(){
      $.Notify({type: 'alert', caption: 'Alert', content: "Server websocket collapsed."});
    }, 2000);
  }

  } catch(exception){
    console.log('Error'+exception);
  }

  //parse a received dotfile package as specified in the protocl
  window.ParsePacket = function ParsePacket()
  {
    var info = JSON.parse(window.dotdata);
    $("#info").text(info[0]);
    window.dotdata = info[1];
    window.startDot();
  }
  window.socket = socket;
}

//request an update of the menu information from the server
window.RequestUpdateMenu = function RequestUpdateMenu()
{
window.state = 2;
//package info according to protocol
window.socket.send(JSON.stringify(["$REQUESTHISTORY", window.schedulers]));
}

//parse package with menu information
window.ParseMenu = function ParseMenu()
{
window.state = 0;
window.menu = JSON.parse(window.menudata);
var html = "<div class=\"accordion\" data-role=\"accordion\" data-close-any=\"true\">\n";

//build the html for the menu in the sidebar
for(var i = 0; i < window.schedulers.length; i++)
{
  if (window.schedulers[i] in window.menu)
  {
    html += "<div class=\"frame\">\n "
    + 			"<div class=\"heading\">" + window.schedulers[i] + "</div>\n "
    +				"<div class=\"content\">\n "
    + 			"<div class=\"listview\">\n ";
    for(var j = 0; j < window.menu[window.schedulers[i]].length; j++)
    {
      var t = new Date(window.menu[window.schedulers[i]][j]*1000);
      var formatted = t.format("dd.mm.yyyy hh:MM:ss");
      html += "<div class=\"list\" onclick=\"window.RequestDotFile('" + window.schedulers[i] + "','" + window.menu[window.schedulers[i]][j] + "')\">\n"
      + 			"<span class=\"list-title\">" + formatted + "</span>\n"
      + 			"</div>\n";
    }
    html += "</div \n "
    + 			"</div>\n "
    + 			"</div>\n "
    +				"</div>\n";
  }
}

html += "</div>\n";
console.log(html);
//render the html in the browser
$("#controls").html(html);
//notify user with banner
setTimeout(function(){
    $.Notify({type: 'info', caption: 'Info', content: "Menu updated"});
}, 2000);
}

//update the scheduling matrix
window.UpdateMatrix = function UpdateMatrix()
{
return;
  //parse the package according to the protocol
var infopackage = JSON.parse(window.matrixdata);
if(infopackage[3] == 2)
{
  //do blacklisting propagation through the matrix
  var cchannel = infopackage[0][0];
  var cslot = infopackage[0][1];
  while(1)
  {
    window.matrix[infopackage[1]][(cchannel+16)%16][cslot] = [2, "Blacklisted"];
    cchannel += 1;
    cslot += 1;
    if (cslot >= 25)
    {
      break;
    }
  }
  cchannel = infopackage[0][0] - 1;
  cslot = infopackage[0][1] - 1;
  while(1)
  {
    window.matrix[infopackage[1]][(cchannel+16)%16][cslot] = [2, "Blacklisted"];
    cchannel -= 1;
    cslot -= 1;
    if (cslot < 0)
    {
      break;
    }
  }
}
else
{
  //using or deusing a cell, update that cell in the matrix object
  window.matrix[infopackage[1]][infopackage[0][0]][infopackage[0][1]] = [infopackage[3], infopackage[2]];
}
//rerender the matrix itself to the screen
window.RenderMatrix(infopackage[1]);
}

//renders the scheduling matrix to the screen. takes the frame to be rendered as inputargument
window.RenderMatrix = function RenderMatrix(frame)
{
//settings for this function
var widthmatrixp = 0.8; //in %/100
var w = window.innerWidth;
var h = window.innerHeight;

//actual function starts here
var numx = window.frameinfo[frame];
var numy = 16;

//calculated settings
var widthmatrix = widthmatrixp * w;
var widthcell = Math.round((widthmatrix - 2 * numx) / numx);

// var html = "<div class=\"tile-container bg-darkCobalt\" style=\"width:" + widthmatrix + "px;\">";
var html = "";
//iterate through the matrix and build the html
for(var y = 0; y < numy; y++)
{
  html += "<div class=\"row\" style=\"width:" + widthmatrix + "px;\">";
  for(var x = 0; x < numx; x++)
  {
    var status = window.matrix[frame][y][x][0];
    var color = "bg-black";

    //color depending on the status of the cell
    switch(status)
    {
      case 0://available
        color = "green";
        break;
      case 1://used
        color = "blue";
        break;
      case 2://blacklisted
        color = "red";
        break;
    }
    // html += "<div class=\"tile-small " + color + "\" style=\"margin: 1px;width:" + widthcell + "px;height:" + widthcell + "px;\">"
    // html += "<div class=\"tile-content slide-down\">";
    // html += "<div class=\"slide\">";
    // html += "</div><div class=\"slide-over bg-darkBlue\" style=\"font-size: 10px;\">";
    // html += window.matrix[frame][y][x][1];
    // html += "</div></div></div>";
    html += "<div id=\"" + frame + "." + y + "." + x + "\"  class=\"tilem " + color + "\" style=\"width:" + (widthcell - 2) + "px; height:" + (widthcell - 2) + "px;\" onclick=\"ClickCell(this)\"></div>";
  }
  html += "</div>";
}

html += "</div>";
//do some css magic to create fancy fade effect
$("#"+frame).removeClass("load");
setTimeout(function() {
  $("#"+frame).html(html);
  $("#"+frame).addClass("load");
}, 500);
}

//send a request for specific dotfile with given scheduler ip and filename (aka timestamp)
window.RequestDotFile = function RequestDotFile(scheduler, dotname)
{
window.socket.send(JSON.stringify(["$REQUESTGRAPH", scheduler, dotname]));
}
