setInterval(() => { renderUsage(); }, 60000);
$('#new').innerHTML = ico('plus') + 'New session'; $('#setbtn').innerHTML = ico('gear') + 'Settings';
post({type:'ready'});
