cd ../
echo "Current Branch:"
git branch
echo "Enter commit message... (type 'void' to skip)"
git add .
read message
if [[ "${message,,}" != "void" ]]; then
	git commit -m "${message}"
	git push
	echo;echo "Commit and push success."
else 
	echo;echo "Commit and push was skipped."
fi

echo "Press Enter to close..."
read
