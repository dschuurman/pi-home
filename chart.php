<html>
<!-- Plot temperature and humidity for last day, month, and year -->
<head>
   <title>pi-home monitor</title>
   <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>

<body>
   <h1>Home Sensor Datalog</h1>

   <p>
      <?php
      # Open Sqlite database
      try {
         $db = new SQLite3('/home/pi/sensor_data.db');
      } catch (Exception $exception) {
         echo '<p>There was an error connecting to the database!</p>';
         echo $exception;
      }
      
      # Use PHP to query sqlite database for latest temperature
      $query = "SELECT * FROM TemperatureHumidity order by datetime DESC LIMIT 1";
      $result = $db->query($query) or die('Query failed');
      $row = $result->fetchArray();
      echo "Last readings at " . $row['datetime'];
      echo "<table>";
      echo "<tr><td>Temperature: </td><td><b>" . number_format((float)$row['temperature'],1) . "</b> &deg;C</td></tr>";
      echo "<tr><td>Relative Humidity: </td><td><b>" . number_format((float)$row['humidity'],1) . "</b>% </td></tr>";
      echo "</table>";
      ?>
   </p>

   <hr>
   <div id='chart_day'></div>
   <hr>
   <div id='chart_month'></div>
   <hr>
   <div id='chart_year'></div>
   <hr>

   <script>
   // Data for last day
   var dayTemperature = {
   x: [  <?php
         echo "\r";
         # Use PHP to query database and build JavaScript array
         $query = "SELECT * FROM TemperatureHumidity where datetime > datetime('now','localtime','-1 day')";
         $result = $db->query($query) or die('Query failed');
         while ($row = $result->fetchArray()) {
            echo "    '" . $row['datetime'] . "',\n";
         }
         ?>
      ],
   y: [  <?php
         echo"\r";
         while ($row = $result->fetchArray()) {
            echo "    " . $row['temperature'] . ",\n";
         }
         ?>
      ],
   name: 'Temperature',
   type: 'scatter'
   };

   var dayHumidity = {
   x: [  <?php
         echo "\r";
         # Use PHP to query database and build JavaScript array
         $query = "SELECT * FROM TemperatureHumidity where datetime > datetime('now','localtime','-1 day')";
         $result = $db->query($query) or die('Query failed');
         while ($row = $result->fetchArray()) {
            echo "    '" . $row['datetime'] . "',\n";
         }
         ?>
      ],
   y: [  <?php
         echo"\r";
         while ($row = $result->fetchArray()) {
            echo "    " . $row['humidity'] . ",\n";
         }
         ?>
      ],
   name: 'Humidity',
   yaxis: 'y2',
   type: 'scatter'
   };

   // combine both y-axes for temperature and humidity
   var dayData = [dayHumidity, dayTemperature];

   // Data for last month
   <?php
   // Number of plot points to use for month and year plots
   define("NUMBER_OF_POINTS", 1000);

   // count number of rows for the past month so that we can limit data to 1000 points on the chart
   $query = "SELECT COUNT() FROM TemperatureHumidity where datetime > datetime('now','localtime','-30 day')";
   $count = intval($db->querySingle($query));
   ?>
   var monthTemperature = {
   x: [  <?php
         echo "\r";
         # Use PHP to query database and build JavaScript array using rougly 1000 points
         $query = "SELECT * FROM TemperatureHumidity where datetime > datetime('now','localtime','-30 day') AND ROWID % ".strval(intval($count/NUMBER_OF_POINTS))." = 0";
         $result = $db->query($query) or die('Query failed');
         while ($row = $result->fetchArray()) {
            echo "    '" . $row['datetime'] . "',\n";
         }
         ?>
      ],
   y: [  <?php
         echo"\r";
         while ($row = $result->fetchArray()) {
            echo "    " . $row['temperature'] . ",\n";
         }
         ?>
      ],
   name: 'Temperature',
   type: 'scatter'
   };

   var monthHumidity = {
   x: [  <?php
         echo "\r";
         # Use PHP to query database and build JavaScript array using rougly 1000 points
         $query = "SELECT * FROM TemperatureHumidity where datetime > datetime('now','localtime','-30 day') AND ROWID % ".strval(intval($count/NUMBER_OF_POINTS))." = 0";
         $result = $db->query($query) or die('Query failed');
         while ($row = $result->fetchArray()) {
            echo "    '" . $row['datetime'] . "',\n";
         }
         ?>
      ],
   y: [  <?php
         echo"\r";
         while ($row = $result->fetchArray()) {
            echo "    " . $row['humidity'] . ",\n";
         }
         ?>
      ],
   name: 'Humidity',
   yaxis: 'y2',
   type: 'scatter'
   };

   // combine both y-axes
   var monthData = [monthHumidity, monthTemperature];

   // Data for last year
   <?php
   // count number of rows for the past year so that we can limit data to 1000 points for chart
   $query = "SELECT COUNT() FROM TemperatureHumidity where datetime > datetime('now','localtime','-365 day')";
   $count = intval($db->querySingle($query));
   ?>

   var yearTemperature = {
   x: [  <?php
         echo "\r";
         # Use PHP to query database and build JavaScript array using rougly 1000 points
         $query = "SELECT * FROM TemperatureHumidity where datetime > datetime('now','localtime','-365 day') AND ROWID % ".strval(intval($count/NUMBER_OF_POINTS))." = 0";
         $result = $db->query($query) or die('Query failed');
         while ($row = $result->fetchArray()) {
            echo "    '" . $row['datetime'] . "',\n";
         }
         ?>
      ],
   y: [  <?php
         echo"\r";
         while ($row = $result->fetchArray()) {
            echo "    " . $row['temperature'] . ",\n";
         }
         ?>
      ],
   name: 'Temperature',
   type: 'scatter'
   };

   var yearHumidity = {
   x: [  <?php
         echo "\r";
         # Use PHP to query database and build JavaScript array using rougly 1000 points
         $query = "SELECT * FROM TemperatureHumidity where datetime > datetime('now','localtime','-365 day') AND ROWID % ".strval(intval($count/NUMBER_OF_POINTS))." = 0";
         $result = $db->query($query) or die('Query failed');
         while ($row = $result->fetchArray()) {
            echo "    '" . $row['datetime'] . "',\n";
         }
         ?>
      ],
   y: [  <?php
         echo"\r";
         while ($row = $result->fetchArray()) {
            echo "    " . $row['humidity'] . ",\n";
         }
         ?>
      ],
   name: 'Humidity',
   yaxis: 'y2',
   type: 'scatter'
   };

   // combine both y-axes for temperature and humidity
   var yearData = [yearHumidity, yearTemperature];

   // Define the layout for the charts
   var layout = {
      title: 'Sensor Data',
      xaxis: {title: 'Date and time'},
      yaxis: {title: 'Temperature (degrees C)'},
      yaxis2: {
         title: 'Relative Humidity (%)',
         overlaying: 'y',
         side: 'right'
      }
   };

   // Draw the charts
   layout.title = 'Sensor data for the past day';
   Plotly.newPlot('chart_day', dayData, layout);
   layout.title = 'Sensor data for the last month';
   Plotly.newPlot('chart_month', monthData, layout);
   layout.title = 'Sensor data for the last year';
   Plotly.newPlot('chart_year', yearData, layout);
   </script>

</body>
</html>