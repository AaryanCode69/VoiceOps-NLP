// Quick test script to see what your VoiceOps API expects
// Run with: node test-api.js

const FormData = require('form-data');
const fs = require('fs');
const https = require('https');
const http = require('http');

async function testAPI() {
    console.log('Testing VoiceOps API...\n');
    
    // Create form data
    const form = new FormData();
    
    // Add a dummy audio file (you can replace with actual file path)
    const dummyAudio = Buffer.from('dummy audio data');
    form.append('audio_file', dummyAudio, {
        filename: 'test.m4a',
        contentType: 'audio/mp4'
    });
    
    console.log('Sending request to: http://127.0.0.1:8000/api/v1/analyze-call');
    console.log('Form fields:', form.getHeaders());
    console.log('\n');
    
    return new Promise((resolve, reject) => {
        const req = http.request({
            method: 'POST',
            host: '127.0.0.1',
            port: 8000,
            path: '/api/v1/analyze-call',
            headers: form.getHeaders()
        }, (res) => {
            let data = '';
            
            res.on('data', (chunk) => {
                data += chunk;
            });
            
            res.on('end', () => {
                console.log('Status Code:', res.statusCode);
                console.log('Response Headers:', res.headers);
                console.log('\nResponse Body:');
                try {
                    console.log(JSON.stringify(JSON.parse(data), null, 2));
                } catch (e) {
                    console.log(data);
                }
                resolve();
            });
        });
        
        req.on('error', (error) => {
            console.error('Request Error:', error);
            reject(error);
        });
        
        form.pipe(req);
    });
}

testAPI().catch(console.error);
