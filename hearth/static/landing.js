let mode = "login";
document.querySelectorAll("[data-auth]").forEach(button => button.addEventListener("click", () => {
  mode = button.dataset.auth;
  document.querySelectorAll("[data-auth]").forEach(b => b.classList.toggle("active", b === button));
  document.querySelector("#auth-form button[type=submit]").textContent = mode === "login" ? "Sign in" : "Create account";
  document.querySelector("#auth-form input[type=password]").autocomplete = mode === "login" ? "current-password" : "new-password";
}));
document.querySelector("#auth-form").addEventListener("submit", async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  if (mode === "signup") data.role = "guardian";
  const response = await fetch(`/api/${mode}`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)});
  const result = await response.json();
  document.querySelector("#auth-message").textContent = result.error || result.message;
  if (response.ok && mode === "login") location.href = "/dashboard";
});
