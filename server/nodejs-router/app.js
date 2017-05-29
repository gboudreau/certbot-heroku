var finalhandler = require('finalhandler')
var http         = require('http')
var Router       = require('router')
 
var router = Router()

// Add this for Let's Encrypt ACME challenge validation
router.get('/.well-known/acme-challenge/:str', function (req, res) {
    res.send(process.env.LETS_ENCRYPT_CHALLENGE);
})
 
var server = http.createServer(function(req, res) {
    router(req, res, finalhandler(req, res))
})
 
server.listen(80)
