cd ECE510-HW-for-AI-ML-Public
echo "Enter commit message..."
git add .
read message
git commit -m "${message}"
git push
