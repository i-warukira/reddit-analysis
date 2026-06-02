(function() {
    var comp = app.project.activeItem;
    if (!(comp instanceof CompItem)) return;

    app.beginUndoGroup("Cinematic Camera Flow");

    // 1. Setup Camera and Controller
    var cameraCtrl = comp.layer("Camera_Controller");
    if (!cameraCtrl) {
        cameraCtrl = comp.layers.addNull();
        cameraCtrl.name = "Camera_Controller";
        cameraCtrl.threeDLayer = true;
    }

    var camera = comp.layer("Tutorial_Camera");
    if (!camera) {
        camera = comp.layers.addCamera("Tutorial_Camera", [960, 540]);
    }
    camera.parent = cameraCtrl;

    // 2. Turn on Depth of Field (The Cinematic Blur)
    camera.cameraOption.depthOfField.setValue(1); // 1 = ON
    camera.cameraOption.aperture.setValue(60); // Aggressive blur
    camera.cameraOption.blurLevel.setValue(100);

    // 3. Clear old camera movement
    var pos = cameraCtrl.transform.position;
    while (pos.numKeys > 0) { pos.removeKey(1); }

    // --- THE CHOREOGRAPHY ---

    // Point A: Focus on Asset (HBAR Heading)
    // Assuming heading is top-leftish. Z=0 means normal distance.
    var posAsset = [600, 300, 0]; 

    // Point B: Lunge to Sidebar (USDC Box)
    // X=1500 pushes camera right. Z=600 pushes camera IN close.
    var posUSDC = [1550, 450, 600]; 

    // Point C: Pan to Multipliers
    // Same X and Z, just panning down (Y goes from 450 to 750)
    var posMultipliers = [1550, 750, 600];

    // --- THE TIMING ---
    // Change these seconds to match your voiceover/timing
    var t1 = 2.0; // Start looking at Asset
    var t2 = 3.0; // SNAP to USDC Box
    var t3 = 5.0; // Start panning down
    var t4 = 5.5; // Arrive at Multipliers

    pos.setValueAtTime(0, posAsset);
    pos.setValueAtTime(t1, posAsset);       // Hold on Asset
    pos.setValueAtTime(t2, posUSDC);        // Lunge to USDC
    pos.setValueAtTime(t3, posUSDC);        // Hold on USDC
    pos.setValueAtTime(t4, posMultipliers); // Pan to Multipliers

    // 4. The "Aggressive Snap" Easing
    // This creates that fast-whip, slow-settle professional motion
    var easeIn = new KeyframeEase(0, 85);  // Come to a very smooth stop
    var easeOut = new KeyframeEase(0, 85); // Take off very fast

    for (var i = 1; i <= pos.numKeys; i++) {
        pos.setTemporalEaseAtKey(i, [easeIn], [easeOut]);
    }

    app.endUndoGroup();
    alert("Camera Flow Built! Preview to see the lunges and blur.");
})();