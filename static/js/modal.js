document.addEventListener("DOMContentLoaded", function () {
    // Récupérer toutes les icônes et noms de joueurs
    const playerElements = document.querySelectorAll(".player-icon, .player-name");

    playerElements.forEach(element => {
        element.addEventListener("click", function () {
            const playerId = this.getAttribute("data-player");
            const modal = document.getElementById(`modal-${playerId}`);

            if (modal) {
                modal.style.display = "flex";
            }
        });
    });

    // Gérer la fermeture des modales
    const closeButtons = document.querySelectorAll(".close");
    closeButtons.forEach(button => {
        button.addEventListener("click", function () {
            const playerId = this.getAttribute("data-player");
            const modal = document.getElementById(`modal-${playerId}`);

            if (modal) {
                modal.style.display = "none";
            }
        });
    });

    // Fermer la modale en cliquant en dehors
    window.addEventListener("click", function (event) {
        if (event.target.classList.contains("modal")) {
            event.target.style.display = "none";
        }
    });
});