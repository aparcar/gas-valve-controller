let table = document.getElementById("states");

async function update_table() {
	table.innerHTML = "<tr><th>Valve</th><th>State</th>"
	fetch('/states.json')
		.then(response => response.json())
		.then(response => {
			for (const valve in response) {
				console.log(valve);
				table.innerHTML += `<tr><td>${valve}</td><td>${response[valve]}</td>`
			}
		});
	console.log("Updated table");
	setTimeout(update_table, 5000);
}

update_table();
